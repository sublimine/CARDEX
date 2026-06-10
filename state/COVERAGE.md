# Cobertura por país — estado vivo

> Números [VERIFICADO] por psql directo sobre `cardex-pg`, 2026-06-10 ~20:15.
> Cada cifra con su método. Esto NO es el techo; es lo blindado HOY mientras la
> máquina corre. El objetivo es el 100% de los puntos de venta de los 6 países.

## Embudo real (la verdad cruda)

| País | Descubiertos (censo) | Con web resuelta | Sirviendo E2E por API | Método de E2E |
|------|---------------------:|-----------------:|----------------------:|---------------|
| 🇳🇱 NL | 38.719 | ~2.955 | **740** | source_entities⋈vehicle_index, kind=dealer |
| 🇩🇪 DE | 26.122 | (en barrido) | 42 | idem (top-up pendiente) |
| 🇫🇷 FR | 18.917 | (parcial) | 161 | idem |
| 🇪🇸 ES | 17.356 | ~1.500 | 193 | idem |
| 🇧🇪 BE | 8.456 | ~1.200 | 164 | idem |
| 🇨🇭 CH | 5.050 | ~1.000 | 183 | idem |
| **TOTAL** | **114.620** | — | **1.484** | — |

Punteros de inventario servidos (coches): **66.594** [psql `vehicle_index` linked].

## Lectura honesta
- **El cuello NO es el scraping: es el DESCUBRIMIENTO de web.** Ejemplo NL: de
  38.719 descubiertos, **26.856 vienen del registro oficial RDW SIN web resuelta**
  + 6.019 de AutoScout sin web propia. La máquina para resolverlos
  (`domain_resolution.worker`) existe y está infrautilizada — es el frente W1.
- **114.620 descubiertos está MUY lejos del universo real** (el owner estima NL
  sola en ~200k puntos de venta). El censo actual cubre una fracción; ampliarlo
  (registros completos, directorios, OSM exhaustivo) es trabajo W1 abierto.
- **1.484 E2E es ~1% del censo y una fracción ínfima del universo.** Es un suelo,
  no un logro. El método correcto (workflows + discovery masivo) es lo que cambia
  la pendiente.

## Multiplicador probado (gate §9.1)
| Familia (receta) | Dealers rindiendo | Punteros | Método |
|------------------|------------------:|---------:|--------|
| datamotive | 53 | 11.750 | psql, config_ref=configs/families/datamotive.json |
| wordpress  | 230 | 5.807 | idem wordpress.json |

## Próxima medición
Cada ciclo: re-correr este cuadro por psql + cruzar con la API (`/v1/entities`
count por país). Disparadores de re-verificación: cifras redondas, ceros, saltos.
