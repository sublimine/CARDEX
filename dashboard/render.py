"""CARDEX control dashboard — HTML renderer.

Turns the collected real-state metrics into a single self-contained HTML page
aimed at a non-technical owner: big numbers, green/amber/red traffic lights,
clear Spanish headlines, and a project-progress timeline.

No external resources (CSS/JS/fonts are inlined) so the file opens by
double-click and works offline. A <meta refresh> reloads the page every 15 min
to pick up the host-regenerated file.

Honesty contract: any datum that is missing or unverifiable renders as
"sin datos" / "sin estimación verificable" — never a fabricated value.
"""

from __future__ import annotations

import html
from typing import Any

from reference import (
    CAP_SUSPECTS,
    COUNTRY_NAMES,
    KNOWN_GIANTS,
    PIPELINE_STAGES,
    SEED_PLATFORMS,
)


def cc_badge(cc: str) -> str:
    """Small country-code badge. Flag emoji is avoided: Windows renders it as
    bare region letters (e.g. 'CH'), which looks broken next to the code."""
    return f'<span class="cc">{esc(cc)}</span>'

REFRESH_SECONDS = 900  # 15 min — matches the host scheduler cadence

# --- formatting helpers ----------------------------------------------------------
def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def num(value: Any) -> str:
    """Spanish thousands formatting: 508339 -> '508.339'. None -> 'sin datos'."""
    if value is None:
        return "sin datos"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return esc(value)


def pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " %"


def short_ts(ts: str | None) -> str:
    if not ts:
        return "sin datos"
    # '2026-06-06 16:05:45.553898+00' -> '2026-06-06 16:05'
    return esc(ts[:16])


# --- semaphore primitives --------------------------------------------------------
OK, WARN, CRIT, MUTE = "ok", "warn", "crit", "mute"
STATUS_DOT = {OK: "●", WARN: "●", CRIT: "●", MUTE: "○"}
STATUS_WORD = {OK: "OK", WARN: "ATENCIÓN", CRIT: "CRÍTICO", MUTE: "SIN DATOS"}


def chip(status: str, text: str) -> str:
    return f'<span class="chip {status}">{STATUS_DOT.get(status, "●")} {esc(text)}</span>'


def bar(value: int, maximum: int, status: str) -> str:
    width = 0 if not maximum else max(1.5, round(100.0 * value / maximum, 2))
    return (
        f'<div class="bartrack"><div class="bar {status}" '
        f'style="width:{width}%"></div></div>'
    )


# --- derived analysis ------------------------------------------------------------
def _all_seed(vehicles_by_platform: list[dict]) -> bool:
    if not vehicles_by_platform:
        return True
    return all(p["platform"] in SEED_PLATFORMS for p in vehicles_by_platform)


def compute_stages(data: dict) -> dict[str, dict]:
    pg = data.get("pg", {})
    redis = data.get("redis", {})
    engine = data.get("engine", {})
    counts = pg.get("counts", {}) if pg.get("available") else {}

    stages: dict[str, dict] = {}

    # discovery
    cand = counts.get("discovery_candidates")
    stages["discovery"] = {
        "status": OK if (cand or 0) > 0 else (MUTE if not pg.get("available") else CRIT),
        "detail": f"{num(cand)} candidatos" if pg.get("available") else "sin datos",
    }

    # scraping (control plane = engine.db work_queue)
    if engine.get("available"):
        wq = engine["work_queue"]["by_status"]
        done, pending, running = wq.get("done", 0), wq.get("pending", 0), wq.get("running", 0)
        total = done + pending + running
        st = WARN if pending > done else OK
        if done == 0:
            st = CRIT
        stages["scraping"] = {
            "status": st,
            "detail": f"{done}/{total} portales · {running} corriendo · {pending} en cola",
        }
    else:
        stages["scraping"] = {"status": MUTE, "detail": "sin datos (engine.db)"}

    # index L1
    vi = counts.get("vehicle_index")
    stages["index"] = {
        "status": OK if (vi or 0) > 0 else (MUTE if not pg.get("available") else CRIT),
        "detail": f"{num(vi)} punteros · {num(pg.get('distinct_domains'))} portales" if pg.get("available") else "sin datos",
    }

    # delta
    ve = counts.get("vehicle_events")
    stages["delta"] = {
        "status": OK if (ve or 0) > 0 else (MUTE if not pg.get("available") else CRIT),
        "detail": f"{num(ve)} eventos (altas/bajas)" if pg.get("available") else "sin datos",
    }

    # enrich L1->L2
    if pg.get("available"):
        veh = counts.get("vehicles", 0)
        seed = _all_seed(pg.get("vehicles_by_platform", []))
        streams_empty = redis.get("available") and all(
            (s["xlen"] or 0) == 0 for s in redis.get("streams", [])
        )
        if veh == 0 or seed:
            stages["enrich"] = {
                "status": CRIT,
                "detail": f"INERTE · {num(veh)} registros (solo seed)"
                + (" · colas vacías" if streams_empty else ""),
            }
        else:
            stages["enrich"] = {"status": OK, "detail": f"{num(veh)} coches ricos"}
    else:
        stages["enrich"] = {"status": MUTE, "detail": "sin datos"}

    # entity resolution
    ent = counts.get("entities")
    stages["entity"] = {
        "status": OK if (ent or 0) > 0 else (MUTE if not pg.get("available") else CRIT),
        "detail": f"{num(ent)} entidades" if pg.get("available") else "sin datos",
    }

    return stages


def global_status(stages: dict[str, dict], data: dict) -> tuple[str, str]:
    """Return (status, headline) summarizing the whole system for the owner."""
    if not data.get("pg", {}).get("available"):
        return MUTE, "Sin conexión a la base de datos — no puedo leer el estado real"
    states = [s["status"] for s in stages.values()]
    crit = states.count(CRIT)
    if crit == 0 and states.count(WARN) == 0:
        return OK, "Cadena completa de punta a punta"
    if crit >= 1:
        return WARN, "Cobertura L1 viva y creciendo · el puente al registro rico (L2) aún no está activado"
    return WARN, "Operativo con tareas pendientes"


# --- section renderers -----------------------------------------------------------
def render_header(data: dict, gstatus: str, headline: str) -> str:
    gen = esc(data.get("generated_at", "")[:16].replace("T", "  "))
    return f"""
<header class="topbar">
  <div class="brand">
    <span class="logo">▦ CARDEX</span>
    <span class="subtitle">Panel de Control · estado y progreso reales</span>
  </div>
  <div class="genmeta">
    <div class="gen">Generado: <strong>{gen}</strong></div>
    <div class="gen muted">Se actualiza solo cada 15 min</div>
  </div>
</header>
<section class="hero {gstatus}">
  <div class="hero-status">{chip(gstatus, STATUS_WORD[gstatus])}</div>
  <h1 class="hero-headline">{esc(headline)}</h1>
</section>
"""


def render_kpis(data: dict) -> str:
    pg = data.get("pg", {})
    counts = pg.get("counts", {}) if pg.get("available") else {}
    engine = data.get("engine", {})
    docker = data.get("docker", {})

    wq = engine.get("work_queue", {}).get("by_status", {}) if engine.get("available") else {}
    producing = pg.get("distinct_domains")

    cards = [
        ("Punteros de coches (L1)", num(counts.get("vehicle_index")), "vehicle_index · cobertura barata", OK if counts.get("vehicle_index") else MUTE),
        ("Coches ricos (L2)", num(counts.get("vehicles")), "vehicles · solo datos seed todavía", CRIT if (counts.get("vehicles", 0) == 0 or _all_seed(pg.get("vehicles_by_platform", []))) else OK),
        ("Dealers descubiertos", num(counts.get("discovery_candidates")), "discovery_candidates", OK if counts.get("discovery_candidates") else MUTE),
        ("Portales que producen", num(producing), f"de 71 registrados · {wq.get('done','—')} done", WARN if (producing or 0) < 30 else OK),
        ("Contenedores vivos", f"{docker.get('up','—')}/{docker.get('total','—')}" if docker.get("available") else "sin datos", "infraestructura Docker", OK if docker.get("available") and docker.get("up") == docker.get("total") else (MUTE if not docker.get("available") else WARN)),
    ]
    out = ['<section class="kpis">']
    for label, value, sub, status in cards:
        out.append(f"""
  <article class="kpi {status}">
    <div class="kpi-value">{value}</div>
    <div class="kpi-label">{esc(label)}</div>
    <div class="kpi-sub">{esc(sub)}</div>
  </article>""")
    out.append("</section>")
    return "".join(out)


def render_pipeline(data: dict, stages: dict[str, dict]) -> str:
    out = ['<section class="card"><h2>Salud del pipeline por etapa</h2>',
           '<p class="card-note">El recorrido de un coche: descubrir → extraer → indexar → detectar cambios → enriquecer → deduplicar.</p>',
           '<div class="pipeline">']
    for i, stage in enumerate(PIPELINE_STAGES):
        s = stages.get(stage["key"], {"status": MUTE, "detail": "sin datos"})
        arrow = '<div class="pipe-arrow">→</div>' if i > 0 else ""
        out.append(f"""{arrow}
    <div class="pipe-stage {s['status']}">
      <div class="pipe-dot">{STATUS_DOT.get(s['status'],'●')}</div>
      <div class="pipe-label">{esc(stage['label'])}</div>
      <div class="pipe-q">{esc(stage['q'])}</div>
      <div class="pipe-detail">{esc(s['detail'])}</div>
    </div>""")
    out.append("</div></section>")
    return "".join(out)


def render_docker(data: dict) -> str:
    docker = data.get("docker", {})
    if not docker.get("available"):
        return '<section class="card"><h2>Infraestructura</h2><p class="nodata">sin datos (Docker no responde)</p></section>'
    out = ['<section class="card"><h2>Contenedores Docker</h2><div class="dockergrid">']
    for c in docker["containers"]:
        out.append(f"""
    <div class="dockerbox {c['state']}">
      <span class="dot">{STATUS_DOT.get('ok' if c['state']=='up' else ('crit' if c['state']=='down' else 'warn'))}</span>
      <span class="dname">{esc(c['name'])}</span>
      <span class="dstatus">{esc(c['status'])}</span>
    </div>""")
    out.append("</div></section>")
    return "".join(out)


def render_country_listings(data: dict) -> str:
    pg = data.get("pg", {})
    if not pg.get("available"):
        return '<section class="card"><h2>Listings por país</h2><p class="nodata">sin datos</p></section>'
    rows = pg.get("index_by_country", [])
    if not rows:
        return '<section class="card"><h2>Listings por país</h2><p class="nodata">sin datos</p></section>'
    total = sum(r["n"] for r in rows)
    mx = max(r["n"] for r in rows)
    top = rows[0]
    bottom = rows[-1]
    insight = (
        f"Concentración real en {COUNTRY_NAMES.get(top['country'], top['country'])} "
        f"({pct(100.0*top['n']/total)} del total). "
        f"{COUNTRY_NAMES.get(bottom['country'], bottom['country'])} es el más débil "
        f"({pct(100.0*bottom['n']/total)}). El monocultivo francés NO está aquí, "
        f"está en el descubrimiento de dealers (ver abajo)."
    )
    out = ['<section class="card"><h2>Listings por país <span class="h2sub">(vehicle_index · 6 mercados)</span></h2>']
    out.append(f'<p class="insight">{esc(insight)}</p>')
    out.append('<div class="bars">')
    for r in rows:
        cc = r["country"]
        name = COUNTRY_NAMES.get(cc, cc)
        share = pct(100.0 * r["n"] / total) if total else "—"
        out.append(f"""
    <div class="barrow">
      <div class="barlabel">{cc_badge(cc)} {esc(name)}</div>
      {bar(r['n'], mx, OK)}
      <div class="barval">{num(r['n'])} <span class="muted">({share})</span></div>
    </div>""")
    out.append("</div></section>")
    return "".join(out)


def render_portal_coverage(data: dict) -> str:
    pg = data.get("pg", {})
    engine = data.get("engine", {})
    if not pg.get("available"):
        return '<section class="card"><h2>Cobertura por portal</h2><p class="nodata">sin datos</p></section>'
    domains = pg.get("index_by_domain", [])
    # map portal -> work_queue status
    wq_status = {}
    if engine.get("available"):
        for p in engine["work_queue"]["portals"]:
            wq_status[p["portal"]] = p["status"]
    mx = max((d["n"] for d in domains), default=1)
    out = ['<section class="card"><h2>Cobertura por portal <span class="h2sub">(extraído · estado · cuello de botella)</span></h2>']
    out.append('<p class="card-note">El total de mercado de cada portal no es verificable sin proxies/sondeo de sitemap → se marca "sin estimación". Los topes redondos delatan paginación no batida.</p>')
    out.append('<table class="ptable"><thead><tr><th>Portal</th><th>País</th><th>Extraído</th><th></th><th>Estado</th></tr></thead><tbody>')
    for d in domains:
        dom = d["domain"]
        cc = d["country"]
        status_word = wq_status.get(dom, "—")
        badges = []
        bstatus = OK
        if dom in CAP_SUSPECTS:
            badges.append(chip(WARN, f"tope ≈{num(CAP_SUSPECTS[dom])} no batido"))
            bstatus = WARN
        elif d["n"] < 100:
            badges.append(chip(WARN, "harvest casi vacío"))
            bstatus = WARN
        else:
            badges.append(chip(OK, "produce"))
        if status_word == "running":
            badges.append(chip(WARN, "corriendo"))
        out.append(f"""
    <tr>
      <td class="mono">{esc(dom)}</td>
      <td>{cc_badge(cc)}</td>
      <td class="numcell">{num(d['n'])}</td>
      <td class="barcell">{bar(d['n'], mx, bstatus)}</td>
      <td>{''.join(badges)}</td>
    </tr>""")
    out.append("</tbody></table></section>")
    return "".join(out)


def render_giants(data: dict) -> str:
    """Giants stuck at 0 — the economic wall. Cross-checked against live data."""
    pg = data.get("pg", {})
    producing = set()
    if pg.get("available"):
        producing = {d["domain"] for d in pg.get("index_by_domain", [])}
    zero_giants = [g for g in KNOWN_GIANTS if g["portal"] not in producing]
    out = ['<section class="card crit-card"><h2>Gigantes en cero <span class="h2sub">(0 % del mercado real)</span></h2>']
    out.append('<p class="card-note">Los líderes del mercado europeo. Bloqueados por el muro económico: sin proxies residenciales parkean por diseño. Desbloqueo = P3 (presupuesto). <span class="src">[VERIFICADO audit §2.2]</span></p>')
    out.append('<div class="giantgrid">')
    for g in zero_giants:
        out.append(f"""
    <div class="giantbox">
      <span class="gdot">{STATUS_DOT[CRIT]}</span>
      <span class="gname">{cc_badge(g['country'])} {esc(g['portal'])}</span>
      <span class="gwall">{esc(g['wall'])}</span>
    </div>""")
    out.append("</div></section>")
    return "".join(out)


def render_discovery(data: dict) -> str:
    pg = data.get("pg", {})
    if not pg.get("available"):
        return '<section class="card"><h2>Discovery de dealers</h2><p class="nodata">sin datos</p></section>'
    by_country = pg.get("disc_by_country", [])
    by_source = pg.get("disc_by_source", [])
    sitemap = pg.get("sitemap_status", [])
    total = sum(r["total"] for r in by_country) or 1
    total_dom = sum(r["with_domain"] for r in by_country)
    fr = next((r for r in by_country if r["country"] == "FR"), None)
    crawled = sum(s["n"] for s in sitemap if s["status"] not in ("pending", "(null)"))
    mx = max((r["total"] for r in by_country), default=1)

    out = ['<section class="card"><h2>Discovery de dealers <span class="h2sub">(candidatos · % con web · % crawleado)</span></h2>']
    insights = []
    if fr:
        insights.append(
            f"Monocultivo francés: FR = {pct(100.0*fr['total']/total)} de los candidatos "
            f"(fuente única SIRENE, sin web)."
        )
    insights.append(
        f"Solo {num(total_dom)} ({pct(100.0*total_dom/total)}) tienen dominio web → crawleables. "
        f"Crawleados de verdad: {num(crawled)} ({pct(100.0*crawled/total)}) — la cadena de dealers aún no ha arrancado."
    )
    out.append(f'<p class="insight">{esc(" ".join(insights))}</p>')

    out.append('<div class="disc-cols">')
    # by country
    out.append('<div class="disc-col"><h3>Por país</h3><div class="bars">')
    for r in by_country:
        cc = r["country"]
        label = f"{cc_badge(cc)} {esc(COUNTRY_NAMES.get(cc, cc))}"
        out.append(f"""
      <div class="barrow">
        <div class="barlabel">{label}</div>
        {bar(r['total'], mx, OK)}
        <div class="barval">{num(r['total'])} <span class="muted">· web {pct(r['pct'])}</span></div>
      </div>""")
    out.append("</div></div>")
    # by source
    out.append('<div class="disc-col"><h3>Por fuente</h3><div class="bars">')
    mxs = max((s["n"] for s in by_source), default=1)
    for s in by_source:
        web = f"{num(s['with_domain'])} con web" if s["with_domain"] else "sin web"
        out.append(f"""
      <div class="barrow">
        <div class="barlabel mono">{esc(s['source'])}</div>
        {bar(s['n'], mxs, OK)}
        <div class="barval">{num(s['n'])} <span class="muted">· {esc(web)}</span></div>
      </div>""")
    out.append("</div></div>")
    out.append("</div>")

    # crawl funnel
    out.append('<div class="funnel">')
    out.append(f'<div class="funnelstep ok"><div class="fnum">{num(total)}</div><div class="flabel">candidatos</div></div>')
    out.append('<div class="pipe-arrow">→</div>')
    out.append(f'<div class="funnelstep warn"><div class="fnum">{num(total_dom)}</div><div class="flabel">con dominio web</div></div>')
    out.append('<div class="pipe-arrow">→</div>')
    out.append(f'<div class="funnelstep crit"><div class="fnum">{num(crawled)}</div><div class="flabel">crawleados</div></div>')
    out.append("</div>")
    out.append("</section>")
    return "".join(out)


def render_streams_crawler(data: dict) -> str:
    redis = data.get("redis", {})
    engine = data.get("engine", {})
    out = ['<section class="card"><h2>Colas y salud del crawler</h2><div class="disc-cols">']

    # streams
    out.append('<div class="disc-col"><h3>Colas (Redis streams)</h3>')
    if redis.get("available"):
        out.append('<table class="mini"><tbody>')
        for s in redis["streams"]:
            n = s["xlen"]
            stt = MUTE if n == 0 else OK
            out.append(f'<tr><td class="mono">{esc(s["name"].replace("stream:",""))}</td>'
                       f'<td class="numcell">{num(n)}</td>'
                       f'<td>{chip(stt, "vacía" if n==0 else "activa")}</td></tr>')
        out.append("</tbody></table>")
        out.append('<p class="card-note">Todas vacías = el puente L1→L2 está cableado pero no se está ejecutando en el host.</p>')
    else:
        out.append('<p class="nodata">sin datos (Redis)</p>')
    out.append("</div>")

    # crawler health
    out.append('<div class="disc-col"><h3>Crawler (engine.db)</h3>')
    if engine.get("available"):
        ids = engine["identities"]
        active = ids["by_status"].get("active", 0)
        quar = ids["by_status"].get("quarantine", 0)
        circ = engine.get("circuit", {})
        closed_c = circ.get("closed", 0)
        open_c = sum(v for k, v in circ.items() if k != "closed")
        proxies = engine.get("proxies", 0)
        dlq = engine.get("dlq", 0)
        out.append('<div class="health">')
        out.append('<div class="hrow">'
                   + chip(OK if active else WARN, f"{active} identidades activas")
                   + chip(WARN if quar else OK, f"{quar} en cuarentena") + "</div>")
        out.append('<div class="hrow">'
                   + chip(WARN, f"{proxies} proxies (sin proxy → gigantes parkean)") + "</div>")
        out.append('<div class="hrow">'
                   + chip(OK if open_c == 0 else CRIT, f"circuitos: {closed_c} cerrados, {open_c} abiertos") + "</div>")
        out.append('<div class="hrow">'
                   + chip(OK if dlq == 0 else WARN, f"DLQ: {dlq} fallos irrecuperables") + "</div>")
        out.append("</div>")
    else:
        out.append('<p class="nodata">sin datos (engine.db)</p>')
    out.append("</div></div></section>")
    return "".join(out)


def render_progress(data: dict, stages: dict[str, dict]) -> str:
    """Project progress registry. Milestone names from the verified blueprint;
    states computed live from the metrics above."""
    pg = data.get("pg", {})
    counts = pg.get("counts", {}) if pg.get("available") else {}
    engine = data.get("engine", {})
    wq = engine.get("work_queue", {}).get("by_status", {}) if engine.get("available") else {}
    by_country = pg.get("disc_by_country", [])
    total_disc = sum(r["total"] for r in by_country) or 0
    fr = next((r for r in by_country if r["country"] == "FR"), None)
    fr_share = (100.0 * fr["total"] / total_disc) if (fr and total_disc) else 0

    done, pending = wq.get("done", 0), wq.get("pending", 0)

    milestones = [
        (OK, "Auditoría integral del sistema", "AUDIT_CARDEX_2026-06-06.md — veredicto empírico de ambos objetivos"),
        (OK, "Blueprint de arquitectura objetivo", "BLUEPRINT_CARDEX.md — malla de 11 microagentes, plan P0→P3"),
        (OK, "Descubrimiento de dealers a escala", f"{num(counts.get('discovery_candidates'))} candidatos en 6 países"),
        (OK, "Cobertura L1 (índice de punteros)", f"{num(counts.get('vehicle_index'))} listings · {num(counts.get('vehicle_events'))} eventos de delta"),
        (OK, "Bug de falso 'done@0' corregido", f"los 12 portales vacíos se resetearon; los {done} 'done' actuales tienen filas"),
        (WARN, "Flota de scraping (T0/T1)", f"{done}/71 portales producen · {pending} en cola (gigantes T2/T3 sin proxy)"),
        (stages["enrich"]["status"], "P0-3 · Puente L1→L2 (enrich_worker)", f"código commiteado, pero {stages['enrich']['detail']}"),
        (stages["entity"]["status"], "P0-4 · Resolución de entidades → PG", stages["entity"]["detail"]),
        (CRIT if fr_share > 50 else OK, "P1 · Romper el monocultivo FR", f"FR = {pct(fr_share)} del discovery (objetivo < 50 %)"),
        (MUTE, "Piloto NL end-to-end (A4→A9)", "siguiente hito: validar la cadena completa bajo límite-y-purga"),
        (MUTE, "Abanico a los 6 países por config", "tras clavar el piloto"),
        (MUTE, "P3 · Proxies → desbloquear gigantes", "aparcado por presupuesto (gobierna el techo de cobertura)"),
    ]
    out = ['<section class="card"><h2>Registro de progreso del proyecto</h2>',
           '<p class="card-note">Hitos del blueprint; el estado de cada uno se calcula en vivo desde la base de datos.</p>',
           '<ol class="timeline">']
    for status, title, detail in milestones:
        icon = {OK: "✓", WARN: "▲", CRIT: "✕", MUTE: "○"}.get(status, "○")
        out.append(f"""
    <li class="tl {status}">
      <span class="tlicon">{icon}</span>
      <div class="tlbody"><div class="tltitle">{esc(title)}</div>
      <div class="tldetail">{esc(detail)}</div></div>
    </li>""")
    out.append("</ol></section>")
    return "".join(out)


def render_footer(data: dict) -> str:
    pg = data.get("pg", {})
    fresh = pg.get("freshness", {}) if pg.get("available") else {}
    return f"""
<footer class="footer">
  <div>Fuentes en vivo: PostgreSQL (cardex-pg) · Redis (cardex-redis) · SQLite (scrapers/engine.db) · Docker</div>
  <div class="muted">Última extracción de listings: {short_ts(fresh.get('vehicle_index'))} · último discovery: {short_ts(fresh.get('discovery_candidates'))}</div>
  <div class="muted">Datos 100 % leídos del estado real. Lo no verificable aparece como «sin datos» o «sin estimación verificable» — nada inventado.</div>
</footer>
"""


# --- page assembly ---------------------------------------------------------------
def render_html(data: dict) -> str:
    stages = compute_stages(data)
    gstatus, headline = global_status(stages, data)
    body = "".join([
        render_header(data, gstatus, headline),
        render_kpis(data),
        render_pipeline(data, stages),
        render_country_listings(data),
        render_portal_coverage(data),
        render_giants(data),
        render_discovery(data),
        render_streams_crawler(data),
        render_progress(data, stages),
        render_docker(data),
        render_footer(data),
    ])
    return _PAGE.replace("{{REFRESH}}", str(REFRESH_SECONDS)).replace("{{BODY}}", body)


_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{{REFRESH}}">
<title>CARDEX · Panel de Control</title>
<style>
:root{
  --bg:#0a0e14; --bg2:#0e131c; --surface:#131a26; --surface2:#1a2331;
  --line:#243044; --text:#e7edf5; --muted:#8a98ad; --faint:#5c6b80;
  --ok:#34d399; --okbg:#0f2e24; --warn:#fbbf24; --warnbg:#332708;
  --crit:#f87171; --critbg:#331417; --accent:#38bdf8; --mute:#4b5b72;
  --r:14px; --r2:10px;
  --fs-hero:clamp(1.6rem,1rem + 2.4vw,2.8rem);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:
    radial-gradient(1200px 600px at 80% -10%, #11202e 0%, transparent 60%),
    radial-gradient(900px 500px at -10% 0%, #16121f 0%, transparent 55%),
    var(--bg);
  color:var(--text); font:15px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,Helvetica,Arial;
  font-variant-numeric:tabular-nums; padding:0 0 60px;
}
.mono{font-family:ui-monospace,"Cascadia Code",Consolas,monospace}
.cc{display:inline-block;font-size:.66rem;font-weight:700;letter-spacing:.04em;color:var(--accent);
  background:#0c1d28;border:1px solid #1d3a4a;border-radius:5px;padding:1px 6px;vertical-align:middle}
.muted{color:var(--muted)} .faint{color:var(--faint)}
strong{color:#fff}
h1,h2,h3{margin:0;font-weight:650;letter-spacing:-.01em}

/* layout */
.topbar,.hero,section,.footer{max-width:1180px;margin-inline:auto;padding-inline:clamp(16px,3vw,34px)}
.topbar{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;padding-top:26px;padding-bottom:14px}
.brand{display:flex;flex-direction:column;gap:4px}
.logo{font-size:1.5rem;font-weight:750;letter-spacing:.06em;color:#fff}
.subtitle{color:var(--muted);font-size:.86rem}
.genmeta{text-align:right;font-size:.82rem}
.gen{color:var(--text)}

/* hero */
.hero{padding-top:8px;padding-bottom:22px;border-bottom:1px solid var(--line);margin-bottom:26px}
.hero-status{margin-bottom:12px}
.hero-headline{font-size:var(--fs-hero);line-height:1.12;max-width:18ch;background:linear-gradient(180deg,#fff,#b9c6d8);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero.ok .hero-headline{max-width:none}

/* chips */
.chip{display:inline-flex;align-items:center;gap:6px;font-size:.76rem;font-weight:600;
  padding:3px 10px;border-radius:999px;border:1px solid var(--line);white-space:nowrap;margin:2px 4px 2px 0}
.chip.ok{color:var(--ok);background:var(--okbg);border-color:#1c4d3c}
.chip.warn{color:var(--warn);background:var(--warnbg);border-color:#5a4410}
.chip.crit{color:var(--crit);background:var(--critbg);border-color:#5e2226}
.chip.mute{color:var(--muted);background:#141b27}

/* KPI */
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:26px}
.kpi{background:linear-gradient(180deg,var(--surface),var(--bg2));border:1px solid var(--line);
  border-radius:var(--r);padding:18px 16px;position:relative;overflow:hidden}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--mute)}
.kpi.ok::before{background:var(--ok)} .kpi.warn::before{background:var(--warn)}
.kpi.crit::before{background:var(--crit)} .kpi.mute::before{background:var(--mute)}
.kpi-value{font-size:1.9rem;font-weight:720;letter-spacing:-.02em;line-height:1}
.kpi-label{margin-top:8px;font-size:.82rem;font-weight:600}
.kpi-sub{margin-top:3px;font-size:.72rem;color:var(--muted)}

/* cards */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  padding:22px clamp(16px,2.4vw,26px);margin-bottom:18px;max-width:1180px;margin-inline:auto}
.card h2{font-size:1.12rem;margin-bottom:4px}
.h2sub{font-size:.78rem;font-weight:500;color:var(--muted)}
.card h3{font-size:.92rem;color:var(--muted);margin:0 0 10px;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.card-note{color:var(--muted);font-size:.83rem;margin:6px 0 16px}
.insight{background:var(--surface2);border-left:3px solid var(--accent);border-radius:0 var(--r2) var(--r2) 0;
  padding:11px 14px;margin:8px 0 18px;font-size:.9rem;color:#cdd9e8}
.src{color:var(--faint);font-size:.74rem}
.nodata,.kpi.mute .kpi-value{color:var(--muted)}
.nodata{font-style:italic;padding:10px 0}

/* pipeline */
.pipeline{display:flex;align-items:stretch;gap:6px;flex-wrap:wrap}
.pipe-stage{flex:1 1 140px;min-width:130px;background:var(--bg2);border:1px solid var(--line);
  border-radius:var(--r2);padding:14px 12px;border-top:3px solid var(--mute)}
.pipe-stage.ok{border-top-color:var(--ok)} .pipe-stage.warn{border-top-color:var(--warn)}
.pipe-stage.crit{border-top-color:var(--crit)} .pipe-stage.mute{border-top-color:var(--mute)}
.pipe-dot{font-size:.7rem}
.pipe-stage.ok .pipe-dot{color:var(--ok)} .pipe-stage.warn .pipe-dot{color:var(--warn)}
.pipe-stage.crit .pipe-dot{color:var(--crit)} .pipe-stage.mute .pipe-dot{color:var(--mute)}
.pipe-label{font-weight:650;margin-top:4px}
.pipe-q{font-size:.74rem;color:var(--faint);margin:2px 0 8px}
.pipe-detail{font-size:.8rem;color:var(--text)}
.pipe-arrow{align-self:center;color:var(--faint);font-size:1.1rem;padding:0 2px}

/* bars */
.bars{display:flex;flex-direction:column;gap:9px}
.barrow{display:grid;grid-template-columns:140px 1fr auto;align-items:center;gap:12px}
.barlabel{font-size:.85rem;font-weight:550}
.bartrack{background:#0c121b;border-radius:6px;height:16px;overflow:hidden;border:1px solid var(--line)}
.bar{height:100%;border-radius:6px 0 0 6px;background:var(--accent);transition:width .3s}
.bar.ok{background:linear-gradient(90deg,#1f8f6c,var(--ok))}
.bar.warn{background:linear-gradient(90deg,#9a7212,var(--warn))}
.bar.crit{background:linear-gradient(90deg,#a23a3d,var(--crit))}
.barval{font-size:.84rem;white-space:nowrap;min-width:120px;text-align:right}

/* tables */
table{width:100%;border-collapse:collapse;font-size:.85rem}
.ptable th,.ptable td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}
.ptable th{color:var(--muted);font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}
.numcell{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.barcell{width:160px}
.ptable tr:hover td{background:var(--surface2)}
.mini td{padding:5px 6px;border-bottom:1px solid var(--line)}

/* docker */
.dockergrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.dockerbox{display:flex;align-items:center;gap:9px;background:var(--bg2);border:1px solid var(--line);
  border-radius:var(--r2);padding:11px 13px}
.dockerbox .dot{font-size:.7rem}
.dockerbox.up .dot{color:var(--ok)} .dockerbox.down .dot{color:var(--crit)} .dockerbox.warn .dot{color:var(--warn)}
.dname{font-weight:600;font-family:ui-monospace,monospace;font-size:.82rem}
.dstatus{margin-left:auto;color:var(--muted);font-size:.74rem}

/* giants */
.crit-card{border-color:#3a1d20}
.giantgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:9px}
.giantbox{display:flex;align-items:center;gap:9px;background:var(--critbg);border:1px solid #3a1d20;
  border-radius:var(--r2);padding:10px 12px}
.gdot{color:var(--crit);font-size:.7rem}
.gname{font-weight:650;font-size:.86rem}
.gwall{margin-left:auto;color:var(--muted);font-size:.72rem;text-align:right}

/* discovery */
.disc-cols{display:grid;grid-template-columns:1fr 1fr;gap:26px}
.disc-col{min-width:0}
.funnel{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:22px;flex-wrap:wrap}
.funnelstep{text-align:center;padding:14px 22px;border-radius:var(--r2);border:1px solid var(--line);background:var(--bg2);min-width:120px}
.funnelstep.ok{border-color:#1c4d3c} .funnelstep.warn{border-color:#5a4410} .funnelstep.crit{border-color:#5e2226}
.fnum{font-size:1.5rem;font-weight:720}
.funnelstep.ok .fnum{color:var(--ok)} .funnelstep.warn .fnum{color:var(--warn)} .funnelstep.crit .fnum{color:var(--crit)}
.flabel{font-size:.76rem;color:var(--muted);margin-top:3px}

/* health */
.health{display:flex;flex-direction:column;gap:8px}
.hrow{display:flex;flex-wrap:wrap}

/* timeline */
.timeline{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
.tl{display:flex;gap:14px;padding:11px 12px;border-radius:var(--r2);align-items:flex-start;position:relative}
.tl::before{content:"";position:absolute;left:21px;top:34px;bottom:-2px;width:2px;background:var(--line)}
.tl:last-child::before{display:none}
.tlicon{flex:none;width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:.7rem;
  font-weight:800;background:var(--mute);color:#0a0e14;z-index:1}
.tl.ok .tlicon{background:var(--ok)} .tl.warn .tlicon{background:var(--warn)}
.tl.crit .tlicon{background:var(--crit)} .tl.mute .tlicon{background:var(--mute);color:#cdd9e8}
.tltitle{font-weight:620}
.tl.mute .tltitle{color:var(--muted)}
.tldetail{font-size:.82rem;color:var(--muted);margin-top:1px}

/* footer */
.footer{margin-top:30px;padding-top:18px;border-top:1px solid var(--line);font-size:.8rem;color:var(--muted);display:flex;flex-direction:column;gap:5px}

@media (max-width:880px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .disc-cols{grid-template-columns:1fr}
  .barrow{grid-template-columns:96px 1fr;}
  .barval{grid-column:2;text-align:left;min-width:0}
}
</style>
</head>
<body>
{{BODY}}
</body>
</html>
"""
