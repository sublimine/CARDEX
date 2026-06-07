---
name: project-discovery-mega
description: "Misión discovery masivo (hacia 2M) — rama feature/discovery-mega, +74.7K dealers vía registros; con-web fronts agotados/bloqueados"
metadata: 
  node_type: memory
  type: project
  originSessionId: c2212611-b904-4b04-9c35-10a7aa492b10
---

Trabajo 2026-06-07 en worktree `C:\Users\elias\projects\cardex-discovery-mega` (rama `feature/discovery-mega` desde main 1ca158a, **NO push**, main intacto; commits bc6e092/640697f/637325f). Informe: `DISCOVERY_MEGA_REPORT.md`. Continúa [[project-discovery-scale]]. Solo escribe `discovery_candidates`; sin migrar esquema, sin reiniciar Docker. Suite 1568 verde. Ejecutado con flota de 5 agentes paralelos.

**Resultado:** total candidatos 685K→**760K (+74.670)**; con_web 46.225→46.526 (+301, casi plano). El salto fue **VOLUMEN vía registros** (identity rows sin web): DE OffeneRegister dump SQLite +47.131, NL RDW censo completo +26.856 (nl_rdw limit=0; era 300). ES OpenMercantil +175 (solo cooperativas/recientes).

**Frentes con-web agotados/bloqueados (HONESTO, evidencia HTTP):**
- OEM menores: solo **Cupra** viable (SNW/D'Ieteren con SEAT); MUERTOS/walled: Mini(STOLO NXDOMAIN), Jeep/PSA(Stellantis DNS/403), Volvo/Mazda/Suzuki(DNS/404), Nissan/Honda/Mitsubishi(sin endpoint sin JS), Mercedes/Ford(Akamai). No hay más OEM coste-cero.
- Directorios 11880-DE(52K, web en detalle) + PagesJaunes-FR(~12% web): Cloudflare rate-limit (Retry-After ~55min) → código OK+testeado, rerun en cooldown/VPS. BE/ES dirs (GoudenGids/PáginasAmarillas/QDQ)=Incapsula→proxy/navegador.
- Registros bloqueados: ES BORME=suscripción; BE KBO=alta email (3 URLs bulk dan 404, be_kbo.py listo p/ KBO_DATA_DIR).
- OSM: `osm_full` (tags expandidos)=MARGINAL (área ya exhaustiva, BE +8); `osm_nametail` (long-tail no-tagueado, name-regex multilingüe bbox+area-guard anti-frontera)=frente con-web vivo, ROI ~68% nuevos/señal 80%/~22% web, proyección ~+1-1.5K con-web, barrido ~7-8h en background (chain bc8mdmd5y).

**2M:** techo libre-host-safe alcanzado; 2M necesita registros de pago + proxies (BE/ES dirs, Akamai OEM) + completar name-tail + Common Crawl. LECCIÓN agentes: dejan procesos background que MUEREN al volver el subagente (re-lanzar yo); dejan basura `__probe_*.py`/tmp (limpiar); ubican tests en sources/ (mover a tests/).
