---
name: project-discovery-free-source-ceiling
description: Discovery scaling reality — free no-auth sources cap ~460K; only France has an open national registry
metadata: 
  node_type: memory
  type: project
  originSessionId: 7f6cd4b0-3b14-43ed-96b1-d0bc7205794d
---

Discovery escaló 9.625 → **460.078 candidatos** (2026-06-06) arreglando fuentes muertas, no añadiendo
muchas nuevas. Reparto: FR 388K · DE 45K · ES 12.8K · NL 5.4K · CH 4.3K · BE 4K.

**Asimetría estructural clave:** Francia es el ÚNICO de los 6 países con registro nacional 100% abierto sin
auth (`recherche-entreprises.api.gouv.fr`, datos INSEE/SIRENE) → 360K solo de ahí. DE/ES/NL/BE/CH **no tienen
equivalente gratis** y quedan a nivel OSM. Por eso FR es el 84% del total.

**Techo de fuentes abiertas sin auth ≈ 460K.** Para 900K hacen falta palancas no-libres o con esfuerzo:
1. Páginas amarillas nacionales (gelbeseiten.de, paginasamarillas.es, goudengids, local.ch) — gratis pero
   requieren stack anti-detección (curl_cffi/Camoufox). Mayor palanca libre restante, sobre todo para DE.
2. Cuentas free con registro: KBO BE, Zefix CH (ambas piden login/creds; KBO bulk = HTTP 302 a login).
3. APIs de pago: Google Places, INSEE bulk, KVK NL.

**Bugs reales que mantenían fuentes a 0** (ya arreglados en commit `00b9478`):
- SIRENE: NAF sin punto (`4511Z`) → HTTP 400. La API exige `45.11Z`.
- OSM: overpass-api.de (mod_security) bloquea UA `python-httpx` → 406. Necesita UA de navegador.

**DDG resolver está bloqueado desde esta IP** (datacenter): html.duckduckgo.com devuelve página sin
`result__a` → todo "no_match". Necesita proxy residencial. crt.sh (name_to_domain, ct_logs) SÍ es alcanzable
pero la query FTS de certwatch es restrictiva (ct_logs solo rindió 367). Ver [[project-discovery-scraping-runtime]].

**Entorno:** hay un auto-commit hook que commitea el trabajo del agente automáticamente — los edits no aparecen
en `git status` porque ya están en HEAD. Verificar con `git show HEAD:<file>`, no con `git diff`.
