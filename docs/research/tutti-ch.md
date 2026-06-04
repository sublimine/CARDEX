# tutti.ch — Investigacion API verificada

**Fecha**: 2026-06-04
**Dominio**: tutti.ch
**Pais**: CH (Suiza)
**Tier**: T1 — Next.js SSR data route, sin WAF (CF Free tier mínimo)
**Inventario estimado**: ~83,396 coches

## Backend

tutti.ch es el mayor portal de clasificados de Suiza (propiedad de TX Group /
Scout24 Schweiz). Frontend Next.js con SSR. Cloudflare Free tier (sin WAF
agresivo). IDs de listado numéricos, URLs SEO con slug regional.

## API Next.js Data Route verificada

```
GET https://www.tutti.ch/_next/data/{buildId}/de/q/autos/{searchToken}.json
    ?page={N}
```

### Verificacion [2026-06-04 via Chrome browser + JS execution]

- Respuesta JSON: `pageProps.dehydratedState.queries[0].state.data`
- Listings en `.listings.edges[].node`
- Cada node: `listingID`, `title`, `seoInformation.deSlug`, `formattedPrice`
- URL de detalle: `https://www.tutti.ch/de/vi/{listingID}/{deSlug}`
- 30 items por pagina
- Cap de paginacion: pagina 101 (101 × 30 = 3,030 items por token)
- `totalCount` en `.listings.totalCount`

### buildId

- Requerido en la ruta: `/_next/data/{buildId}/...`
- Cambia con cada deploy
- Se extrae del `__NEXT_DATA__` JSON embebido en el HTML de `/de`
- Mismo patron que viabovag.nl

### Search Token — formato MessagePack

El token en la URL es un blob msgpack codificado en base64url con prefijo 'A':

```
token = 'A' + base64url_encode(msgpack([
    None,                   # reservado
    'cars',                 # categoria
    [
        brand_filters,      # slot 0: filtros single-select (marca)
        None,               # slot 1: reservado
        range_filters,      # slot 2: filtros de rango (precio, año)
        None,               # slot 3: reservado
    ]
]))
```

#### Filtros single-select (slot 0)

```python
# Sin filtro de marca:
None

# Con filtro de marca:
[['carsAutoScoutBrand', 'bmw']]  # lista de pares [nombre, valor]
```

#### Filtros de rango (slot 2)

```python
# Sin filtro de rango:
None

# Solo max precio:
[['price', False, None, 20000]]  # [nombre, False, min_o_None, max_o_None]

# Min + max precio:
[['price', False, 10000, 30000]]  # Boolean siempre False

# Precio + año:
[['price', False, 10000, 30000], ['carsAutoScoutRegYear', False, 2020, 2026]]
```

#### Tokens verificados

| Descripcion | totalCount | Token |
|---|---|---|
| Base (todos) | 83,396 | `Ak8CkY2Fyc5TAwMDA` |
| BMW | 7,614 | `Ak8CkY2Fyc5SRkrJjYXJzQXV0b1Njb3V0QnJhbmSjYm13wMDA` |
| VW | 10,375 | `Ak8CkY2Fyc5SRkrJjYXJzQXV0b1Njb3V0QnJhbmSidnfAwMA` |
| BMW ≤20k CHF | 3,687 | `Ak8CkY2Fyc5SRkrJjYXJzQXV0b1Njb3V0QnJhbmSjYm13wJGUpXByaWNlwsDNTiDA` |
| BMW 10k-30k CHF | 3,343 | (construido + verificado) |

### Slug URL

El segmento de ruta (e.g. `autos-bmw`) es COSMÉTICO. El servidor ignora el
slug y solo interpreta el token. Verificado: token BMW con slug `autos`
devuelve 7,614 resultados BMW correctamente.

### Marcas disponibles

391 marcas en el filtro `carsAutoScoutBrand`. Las ~37 marcas principales
cubren >95% del inventario. Valores: `"vw"`, `"bmw"`, `"mercedes-benz"`,
`"audi"`, `"toyota"`, `"ford"`, etc.

## Estrategia de scraping

Brand-partitioned paginator con sub-particion por precio:

1. **Particion primaria**: una entrada por marca (top ~37 marcas)
2. **Paginacion**: pagina 1..101 via `?page=N` (30 items/pagina)
3. **Sub-particion**: marcas con >3,030 items se subdividen por banda de precio
4. **buildId**: resuelto dinámicamente desde HTML SSR
5. **Token**: construido con msgpack desde parametros del segmento
6. **Cobertura**: >95% del inventario via marcas principales

## Notas

- domain_map.py: entrada para tutti.ch (T1, WAF.CF_FREE)
- El buildId debe resolverse dinamicamente (cambia con deploys)
- Las URLs de detalle son absolutas: `https://www.tutti.ch/de/vi/{id}/{slug}`
- msgpack requerido como dependencia para construir tokens
- anibis.ch comparte el mismo backend (Scout24 Schweiz) con frontend FR
