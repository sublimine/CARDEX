# 2dehands.be — Investigación API verificada

**Fecha**: 2026-06-04
**Dominio**: 2dehands.be (alias: tweedehands.be)
**País**: BE (Bélgica)
**Tier**: T0 — API JSON abierta, sin WAF
**Inventario estimado**: ~102,000 coches

## Backend

2dehands.be es propiedad de Adevinta y comparte backend con marktplaats.nl.
El frontend es en francés/neerlandés pero la API LRP es idéntica.

## API LRP verificada

```
GET https://www.2dehands.be/lrp/api/search
    ?l1CategoryId=91
    &offset={N}
    &limit=30
    &attributeRanges[]=constructionYear:{from}:{to}
    &attributeRanges[]=PriceCents:{from_cents}:{to_cents}
    &sortBy=SORT_INDEX
    &sortOrder=DECREASING
```

### Verificación [2026-06-04 via Chrome browser]

- `l1CategoryId=91` = "Auto's" (coches), misma categoría que marktplaats.nl
- Respuesta JSON idéntica: `listings[]` con `vipUrl`, `itemId`, `title`, `priceInfo`
- `maxAllowedPageNumber=167` → ventana máxima ~5,010 listings por query
- Filtros `attributeRanges[]` funcionan idénticamente (año, precio en céntimos)
- Sin Cloudflare, sin WAF — responde 200 a cliente desnudo
- URLs de detalle: `vipUrl` relativo → prefijo `https://www.2dehands.be`

### Paginación

- `offset` + `limit=30`
- `maxAllowedPageNumber=167` (idéntico a marktplaats)
- Offset > ventana → `listings[]` vacío (sin error)

### Filtros año/precio

- `attributeRanges[]=constructionYear:2018:2020` (inclusivo)
- `attributeRanges[]=PriceCents:1000000:2000000` (valor en CÉNTIMOS)

## Estrategia de scraping

Clon directo de `MarktplaatsNLScraper`:
- Misma grid year×price
- Misma subdivisión de celdas capadas
- Mismo parsing de `listings[].vipUrl`
- Solo cambia: HOST, DOMAIN, COUNTRY

## Notas

- domain_map.py ya tiene entrada para `tweedehands.be` (T0, WAF.NONE)
- El dominio registrado en CARDEX es `2dehands.be` (nombre primario del sitio)
