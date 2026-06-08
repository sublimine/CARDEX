#!/usr/bin/env python3
"""cardex monitor — real-time control room, served as a governed worker.

Pure-stdlib HTTP server (no deps). Reads the EXISTING state sources every request
(supervisor_state.json, tier1_progress.json, logs/*.log) — never duplicates state.
Serves:
  /            -> self-contained auto-refreshing dashboard (fetches /api/state ~2.5s)
  /api/state   -> live JSON: workers, coverage ledger, queue progress, log tails

Heartbeats to CARDEX_HB so the supervisor governs it (restart on death). Bound to
127.0.0.1:8787 (local only). Open: http://localhost:8787
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
EVID = REPO / "stealth" / "evidence"
STATE = ROOT / "supervisor_state.json"
LEDGER = EVID / "tier1_progress.json"
LOGS = ROOT / "logs"
HB = os.environ.get("CARDEX_HB", str(ROOT / "hb" / "monitor.hb"))
PORT = int(os.environ.get("CARDEX_MONITOR_PORT", "8787"))


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def beat_loop():
    while True:
        try:
            Path(HB).write_text(str(time.time()))
        except Exception:
            pass
        time.sleep(5)


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def tail(p: Path, n: int = 40) -> list[str]:
    try:
        data = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return data[-n:]
    except Exception:
        return []


def current_profiler_log() -> tuple[str, list[str]]:
    """Find the most-recently-modified profiler/worker log to tail (the 'reasoning')."""
    cands = list(LOGS.glob("profiler_*.log")) + list(LOGS.glob("tier1_runner.log"))
    cands = [c for c in cands if c.exists()]
    if not cands:
        return "", []
    newest = max(cands, key=lambda c: c.stat().st_mtime)
    return newest.name, tail(newest, 30)


def build_state() -> dict:
    sup = read_json(STATE) or {}
    led = read_json(LEDGER) or {}
    prof_name, prof_lines = current_profiler_log()
    portals = []
    for k, v in led.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        portals.append({"portal": k, **{kk: v.get(kk) for kk in
                        ("total_oficial", "cobertura", "pct", "estado", "makes_done")}})
    portals.sort(key=lambda p: (p.get("pct") is None, -(p.get("pct") or 0)))
    return {
        "ts": now_iso(),
        "supervisor": {"pid": sup.get("supervisor_pid"), "ts": sup.get("ts"),
                       "tick_s": sup.get("tick_s")},
        "workers": sup.get("workers", []),
        "portals": portals,
        "meta": led.get("_meta", {}),
        "supervisor_log": tail(LOGS / "supervisor.log", 18),
        "profiler_log": {"name": prof_name, "lines": prof_lines},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence access logs
        pass

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            body = json.dumps(build_state(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")


PAGE = r"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CARDEX · Sala de Control</title>
<style>
:root{--bg:#0a0e14;--surface:#131a26;--surface2:#1a2331;--line:#243044;--text:#e7edf5;
--muted:#8a98ad;--ok:#34d399;--warn:#fbbf24;--crit:#f87171;--accent:#38bdf8;--mute:#4b5b72}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 80% -10%,#11202e,transparent 60%),var(--bg);
color:var(--text);font:14px/1.5 ui-sans-serif,system-ui,"Segoe UI",Roboto,Arial;font-variant-numeric:tabular-nums}
.wrap{max-width:1280px;margin:0 auto;padding:18px clamp(14px,2.5vw,30px) 50px}
header{display:flex;justify-content:space-between;align-items:baseline;gap:16px;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:18px}
.logo{font-size:1.4rem;font-weight:750;letter-spacing:.05em}.sub{color:var(--muted);font-size:.82rem}
.live{display:inline-flex;align-items:center;gap:7px;color:var(--ok);font-weight:600;font-size:.82rem}
.dot{width:9px;height:9px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 rgba(52,211,153,.6);animation:p 1.6s infinite}
@keyframes p{0%{box-shadow:0 0 0 0 rgba(52,211,153,.5)}70%{box-shadow:0 0 0 8px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:22px 0 10px;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .v{font-size:1.9rem;font-weight:720;line-height:1}.kpi .l{color:var(--muted);font-size:.76rem;margin-top:6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
table{width:100%;border-collapse:collapse;font-size:.84rem}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}
.num{text-align:right;font-weight:600}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:.74rem;font-weight:600;padding:2px 9px;border-radius:999px;border:1px solid var(--line)}
.ok{color:var(--ok);background:#0f2e24;border-color:#1c4d3c}.warn{color:var(--warn);background:#332708;border-color:#5a4410}
.crit{color:var(--crit);background:#331417;border-color:#5e2226}.mute{color:var(--muted);background:#141b27}
.bar{height:8px;border-radius:5px;background:#0c121b;border:1px solid var(--line);overflow:hidden;margin-top:4px}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#1f8f6c,var(--ok))}
.log{background:#0b0f16;border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-family:ui-monospace,Consolas,monospace;
font-size:.76rem;color:#b6c2d4;height:240px;overflow:auto;white-space:pre-wrap;line-height:1.4}
.log .r{color:var(--crit)}.log .s{color:var(--ok)}.log .w{color:var(--warn)}
@media(max-width:880px){.kpis{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<header><div><div class="logo">▦ CARDEX · Sala de Control</div><div class="sub" id="sub">conectando…</div></div>
<div class="live"><span class="dot"></span><span id="livetxt">EN VIVO</span></div></header>
<div class="kpis" id="kpis"></div>
<h2>Workers gobernados</h2><div class="card"><table id="workers"><thead><tr><th>Worker</th><th>PID</th><th>Estado</th><th>Heartbeat</th><th class="num">Reinicios</th></tr></thead><tbody></tbody></table></div>
<h2>Cobertura por portal (Σ facetas ≈ total · pendiente de verificación Guardian)</h2><div class="card"><table id="portals"><thead><tr><th>Portal</th><th class="num">Total oficial</th><th class="num">Cobertura</th><th class="num">%</th><th>Estado</th></tr></thead><tbody></tbody></table></div>
<h2>Razonamiento en vivo (logs)</h2><div class="grid">
<div class="card"><div class="sub">supervisor.log</div><div class="log" id="suplog"></div></div>
<div class="card"><div class="sub" id="proflbl">worker en curso</div><div class="log" id="proflog"></div></div>
</div>
<div class="sub" style="margin-top:14px" id="foot"></div>
</div><script>
const $=s=>document.querySelector(s);
function n(x){return x==null?'—':Number(x).toLocaleString('es-ES')}
function chip(t,c){return `<span class="chip ${c}">${t}</span>`}
function wstatus(s){if(!s)return chip('?','mute');if(s.includes('alive'))return chip(s,'ok');if(s.includes('restart')||s.includes('backoff'))return chip(s,'warn');if(s.includes('dead')||s.includes('down'))return chip(s,'crit');return chip(s,'mute')}
function colorLog(lines){return lines.map(l=>{let c='';if(/restart|unhealthy|FAIL|error|dead/i.test(l))c='r';else if(/started|alive|OK|launched/i.test(l))c='s';else if(/backoff|warn|hung/i.test(l))c='w';return c?`<span class="${c}">${esc(l)}</span>`:esc(l)}).join('\n')}
function esc(s){return (s||'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]))}
async function tick(){try{
 const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();
 const m=d.meta||{};
 $('#kpis').innerHTML=[
   ['Cola tier-1',n(m.queue_total||70)],
   ['Medidos / en curso',n(m.medidos_o_en_curso)],
   ['Pendientes de perfil',n(m.pendientes_de_perfil)],
   ['Supervisor PID',d.supervisor.pid||'—']
 ].map(k=>`<div class="kpi"><div class="v">${k[1]}</div><div class="l">${k[0]}</div></div>`).join('');
 $('#workers').querySelector('tbody').innerHTML=(d.workers||[]).filter(w=>w.enabled!==false).map(w=>
   `<tr><td>${esc(w.name)}</td><td>${w.pid||'—'}</td><td>${wstatus(w.status)}</td><td>${esc((w.status||'').match(/hb (\d+s)/)?.[1]||'—')}</td><td class="num">${w.restarts||0}</td></tr>`).join('');
 $('#portals').querySelector('tbody').innerHTML=(d.portals||[]).map(p=>{
   let c=p.pct>=99?'ok':(p.pct>=50?'warn':(p.pct==null?'mute':'crit'));
   let pctTxt=p.pct==null?'—':(p.pct+'%');
   let barb=p.pct==null?'':`<div class="bar"><i style="width:${Math.min(100,p.pct)}%"></i></div>`;
   let est=p.estado||'';let ec=est.includes('verificaci')?'ok':(est.includes('midiendo')?'warn':(est.includes('BLOQ')?'crit':'mute'));
   return `<tr><td>${esc(p.portal)}</td><td class="num">${n(p.total_oficial)}</td><td class="num">${n(p.cobertura)}</td><td class="num">${pctTxt}${barb}</td><td>${chip(esc(est),ec)}</td></tr>`}).join('');
 const sl=$('#suplog');sl.innerHTML=colorLog(d.supervisor_log||[]);sl.scrollTop=sl.scrollHeight;
 const pl=$('#proflog');pl.innerHTML=colorLog((d.profiler_log||{}).lines||[]);pl.scrollTop=pl.scrollHeight;
 $('#proflbl').textContent=(d.profiler_log||{}).name||'worker en curso';
 $('#sub').textContent='actualizado '+ (d.ts||'').replace('T',' ');
 $('#foot').textContent='Fuentes en vivo: supervisor_state.json · tier1_progress.json · logs/*.log — refresco 2,5 s';
 $('#livetxt').textContent='EN VIVO';
}catch(e){$('#livetxt').textContent='reintentando…'}}
tick();setInterval(tick,2500);
</script></body></html>"""


def main() -> int:
    threading.Thread(target=beat_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    sys.stdout.write(f"[monitor] serving http://localhost:{PORT} pid={os.getpid()}\n"); sys.stdout.flush()
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
