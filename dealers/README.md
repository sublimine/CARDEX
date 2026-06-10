# /dealers — clasificación masiva por geografía

Estructura: `/dealers/{ISO}/{PROV}/{CIUDAD}/{cdx_code}/`

Cada hoja de dealer contiene:
- `ficha.json` — identidad (`cdx_code`), geo (país→provincia→ciudad), URL de stock
  confirmada, contacto.
- `estado.json` — último gate superado (W1..W5), `inventory_count`, último delta,
  checksum del dato estructurado (para reconstrucción en frío, V5).
- (la receta NO se duplica aquí: vive en `configs/dealers/{domain}.json` o
  `configs/families/{cms}.json` y se referencia por `config_ref`).

## Identidad
- `cdx_code` = `CDX-<ISO2>-<8 base32>` — INMUTABLE, derivado del dominio
  (`scrapers/intelligence/cdx_code.py`). Mismo dealer físico → mismo código aunque
  se redescubra por otra fuente. Es la hoja del path.
- La ruta `{ISO}/{PROV}/{CIUDAD}` da la jerarquía navegable; la hoja `cdx_code` da
  la estabilidad. Ver `workflows/README.md` §D1 para el porqué (el SEQ es frágil).

> Esta carpeta se puebla por W5 al cerrar cada dealer end-to-end. Vacía hoy salvo
> este README — el piloto ES (Task #9) escribe el primer dealer.
