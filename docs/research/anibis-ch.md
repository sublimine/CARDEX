# anibis.ch — Investigación API

> Portal suizo de clasificados, frontend francés. Gemelo idéntico de tutti.ch
> sobre el mismo backend Scout24. ~78k coches. Cloudflare Free tier.

**Fecha de verificación**: 2026-06-04

## Arquitectura

Frontend Next.js SSR. Mismo backend que tutti.ch (Scout24 Switzerland AG).
Los tokens de búsqueda son **idénticos** a tutti.ch — codificados en MessagePack
con prefijo `A` + base64url. El mismo token produce el mismo resultado en ambos
dominios (inventario compartido).

## Data Route

```
GET https://www.anibis.ch/_next/data/{buildId}/fr/q/voitures/{token}.json?page={N}
```

- **buildId**: dinámico, extraído de `__NEXT_DATA__` en HTML SSR de `/fr`
- **token**: `A` + base64url(msgpack([None, 'cars', [brand_filters, None, range_filters, None]]))
- **Paginación**: `?page=N` (N >= 2); 30 items/página; cap en 101 páginas (3,030 items)

## Estructura de Respuesta

```
pageProps.dehydratedState.queries[0].state.data.listings.edges[].node
  ├── listingID: str
  └── seoInformation
        ├── deSlug: str
        ├── frSlug: str   ← usar este para URLs de detalle
        └── itSlug: str
```

## URL de Detalle

```
https://www.anibis.ch/fr/vi/{listingID}/{frSlug}
```

## Diferencias con tutti.ch

| Campo | tutti.ch | anibis.ch |
|-------|----------|-----------|
| HOST | www.tutti.ch | www.anibis.ch |
| Prefijo idioma | /de/ | /fr/ |
| Slug categoría | autos | voitures |
| Slug detalle | deSlug | frSlug |
| Token | idéntico | idéntico |
| Inventario | compartido | compartido |

## Tokens Verificados

| Filtro | Token | Resultado |
|--------|-------|-----------|
| Base (todos) | `Ak8CkY2Fyc5TAwMDA` | ~78,401 |
| BMW | `Ak8CkY2Fyc5SRkrJjYXJzQXV0b1Njb3V0QnJhbmSjYm13wMDA` | 7,124 |

## Estrategia

Clon directo de TuttiCHScraper con 4 constantes modificadas:
HOST, LANG, CATEGORY_SLUG, SLUG_KEY. La clase hereda toda la lógica
de tokens, partición por marca y subdivisión por precio.
