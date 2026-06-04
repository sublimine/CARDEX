# autolina.ch — Investigación API

> Portal suizo de coches de ocasión (~94k coches). API REST abierta en
> subdominio mobile. Sin WAF en API. Cloudflare en frontend web.

**Fecha de verificación**: 2026-06-04

## API

```
GET https://m.autolina.ch/api/v2/searchcars?limit={L}&offset={O}
```

- **limit**: máximo probado 100 (funciona sin cap)
- **offset**: paginación por offset, sin tope; offset > count devuelve `cars: []`
- **Filtrado server-side**: NO disponible. `makeId=X` es ignorado; `make=X` retorna 0.
  El scraper pagina linealmente sobre todo el inventario.

## Respuesta

```json
{
  "status": 1,
  "data": {
    "count": "94637",
    "cars": [
      {
        "carId": 4658983,
        "makeSlug": "vw",
        "modelSlug": "touareg",
        "slug": "vw-touareg",
        "makeName": "VW",
        "modelName": "TOUAREG",
        "modelType": "Touareg Geländewagen Diesel 4.0 V8 TDI R-Line",
        "price": 65000,
        "mileage": 59000,
        "constructionYear": "2020",
        "region": "ZH",
        "city": "Egg b. Zürich",
        "postalCode": "8132",
        "isNew": false,
        "isDealer": true,
        "dealerName": "...",
        "pics": [...],
        ...
      }
    ]
  }
}
```

## URL de Detalle

```
https://www.autolina.ch/auto/{slug}/{carId}
```

Ejemplo: `https://www.autolina.ch/auto/vw-touareg/4658983`

## Paginación Verificada

| offset | limit | cars.length | Notas |
|--------|-------|-------------|-------|
| 0 | 3 | 3 | OK |
| 3 | 3 | 3 | OK — diferentes carIds |
| 0 | 50 | 50 | OK |
| 0 | 100 | 100 | OK |
| 10000 | 100 | 100 | OK — deep pagination funciona |
| 94600 | 100 | 0 | Correcto — más allá del inventario |

## WAF / Anti-bot

- `www.autolina.ch`: Cloudflare managed challenge (Turnstile)
- `m.autolina.ch`: **sin WAF** — API REST abierta, responde JSON directo
- `api.autolina.ch`: solo imágenes (CDN)

## Estrategia

Scraper single-segment (como gaspedaal.nl/viabovag.nl):
- `partition_params()` → `[{}]`
- `subdivide_segment()` → `[]`
- `fetch_segment()` → GET offset/limit, parse JSON, extraer URLs
- PAGE_SIZE=100, MAX_PAGES=1000 (100 × 1000 = 100,000 > inventario actual)
- Tier T0 — sin anti-bot, sin WAF
