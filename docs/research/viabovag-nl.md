# viabovag.nl — Investigacion API verificada

**Fecha**: 2026-06-04
**Dominio**: viabovag.nl
**Pais**: NL (Paises Bajos)
**Tier**: T1 — Next.js SSR data route, sin WAF (IIS backend)
**Inventario estimado**: ~129,069 coches

## Backend

viaBOVAG.nl es la plataforma online de la red de concesionarios BOVAG en Paises
Bajos. Frontend Next.js con SSR. Sin Cloudflare/Akamai/DataDome. IIS backend.

## API Next.js Data Route verificada

```
GET https://www.viabovag.nl/_next/data/{buildId}/srp.json
    ?mobilityType=auto
    &selectedFilters=pagina-{N}
```

### Verificacion [2026-06-04 via Chrome browser]

- Respuesta JSON con `pageProps.serverSearchResults.results[]`
- Cada resultado: `url` (absoluto), `friendlyUriPart`, `vehicle.brand/model/year`, `price`
- 24 items por pagina
- `count` = 129,069 (total global, NO filtrado)
- Paginacion via `selectedFilters=pagina-N` en query params
- Cap de paginacion: pagina 4167. Paginas 4168+ devuelven datos identicos a 4167
- Alcance: 4167 x 24 = 100,008 URLs unicas (~77% del inventario)

### buildId

- Requerido en la ruta: `/_next/data/{buildId}/srp.json`
- Cambia con cada deploy de la aplicacion
- Se extrae del `__NEXT_DATA__` JSON embebido en el HTML de cualquier pagina
- HTML en `/auto` o `/auto/pagina-N` contiene `__NEXT_DATA__` con `buildId`

### Filtros

- `selectedFilters=pagina-N`: FUNCIONA para paginacion
- `selectedFilters=volkswagen` (marca): NO funciona (devuelve 0 resultados)
- `YearFrom=2020&YearTo=2022` (query params directos): IGNORADOS por el servidor
- `Brand=volkswagen` (query param directo): IGNORADO (devuelve inventario completo)
- Path filters (`/auto/bouwjaar-2020-tm-2022`): NO funcionan en SSR (0 resultados)
- Conclusion: solo paginacion funciona server-side; filtros son client-side only

### Estructura de items

```json
{
  "id": "uuid",
  "mobilityType": "auto",
  "url": "https://www.viabovag.nl/auto/aanbod/renault-clio-...-9qf4io7",
  "friendlyUriPart": "renault-clio-...-9qf4io7",
  "price": 21895,
  "vehicle": {
    "brand": "Renault",
    "model": "Clio",
    "year": 2024,
    "mileage": 39409,
    "fuelTypes": ["benzine", "hybride"]
  },
  "company": { ... }
}
```

## Estrategia de scraping

Single-segment global paginator (como gaspedaal.nl):
- Particion: segmento unico vacio
- Paginacion: pagina 1..4167 via Next.js data route
- Deteccion de cap: paginas que devuelven solo URLs ya vistas = cap alcanzado
- buildId: resuelto en la primera request via HTML SSR
- Cobertura: ~100k de ~129k (77%). Filtros server-side no disponibles.

## Notas

- domain_map.py necesita entrada para viabovag.nl (T1, WAF.NONE)
- El buildId debe resolverse dinamicamente (cambia con deploys)
- Las URLs de detalle son absolutas en la respuesta — no necesitan prefijo
