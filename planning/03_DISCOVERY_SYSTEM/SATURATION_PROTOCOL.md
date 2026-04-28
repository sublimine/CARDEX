# Saturation Protocol — Definición operacional de exhaustividad de discovery

## Identificador
- Documento: SATURATION_PROTOCOL
- Versión: 1.0
- Fecha: 2026-04-14
- Estado: AUTORITATIVO

## Propósito
Definir el protocolo cuantitativo y verificable mediante el cual se declara que una fase de discovery ha alcanzado saturación, según el principio R4 (sin techos mentales). El protocolo establece cuándo es legítimo pasar de "estoy descubriendo" a "he descubierto todo lo descubrible con los vectores actuales" y cuándo es obligatorio buscar vectores adicionales.

## Niveles de saturación

### Nivel 1 — Saturación por familia individual
Se declara cuando una familia específica, ejecutada hasta sus límites naturales (todas las fuentes consultadas, todas las queries ejecutadas, todos los cross-references hechos), no produce discoveries nuevos durante el T_family_saturation calibrado.

### Nivel 2 — Saturación por país
Se declara cuando todas las 15 familias activas, ejecutadas en secuencia sobre un país, producen delta cero de nuevos dealers durante 3 ciclos consecutivos.

### Nivel 3 — Saturación global (6 países)
Nivel 2 alcanzado en los 6 países simultáneamente.

### Nivel 4 — Saturación permanente
Nivel 3 sostenido durante ≥6 meses con monitoreo continuo. Permite declarar el knowledge graph "estable" y transicionar a modo mantenimiento (solo detectar cambios, no discovery masivo).

## Métricas y thresholds por nivel

### Nivel 1

Para cada familia F y país P:
- `new_dealers_discovered_by_F_in_P_per_cycle` → track serie temporal
- Ventana móvil de N=5 ciclos
- Saturación cuando: max(new_dealers) en ventana < threshold_family(F) durante T_family_saturation

Donde `T_family_saturation` varía por familia:
- Familias con datos estáticos (A, G, H, I): T = 1 mes
- Familias con datos dinámicos (C Common Crawl): T = 3 meses
- Familias con discovery long-tail (K, L, O): T = 6 meses

Y `threshold_family(F)` se calibra como:
- Familias autoritativas (A, H): <5 dealers nuevos/ciclo
- Familias secundarias (B, F, G): <10/ciclo
- Familias long-tail (K, O): <20/ciclo

### Nivel 2

Para cada país P:
- Condition: 3 ciclos consecutivos de TODAS las familias con delta = 0 dealers
- Ciclo duration: 2 semanas
- Ventana total: 6 semanas
- Monitoring de false-zero (familia caída, no saturada) → si una familia no ejecutó correctamente, el ciclo no cuenta
- Health-check pre-cycle: cada familia reporta su estado (executed_successfully, sources_accessed_N_of_M, errors) → si <95% sources OK, ciclo marcado como invalid

### Nivel 3

AND lógico sobre los 6 países. Cada país independientemente debe cumplir Nivel 2.

### Nivel 4

Sostener Nivel 3 durante 6 meses. Transición a:
- Reducción de frecuencia de discovery (bimensual en lugar de quincenal)
- Focus en delta-detection (nuevas aperturas, cierres)
- Liberación de recursos compute hacia extraction + quality

## Protocolo de búsqueda de vectores nuevos tras saturación

Tras declarar Nivel 2 en un país, se ejecuta el **gap analysis protocol**:

1. **Análisis cualitativo del universo descubierto:**
   - Distribución por tamaño (dealers con N vehículos publicados)
   - Distribución geográfica (dealers por NUTS-3 region)
   - Distribución por NACE code
   - Distribución por año de fundación
   - Distribución por tipo (oficial/independiente/multi-brand/especialista)

2. **Comparación con denominadores de referencia:**
   - Matriculaciones per capita per región (¿está la densidad dealer consistente?)
   - Parc per capita (¿hay regiones con muchos coches y pocos dealers descubiertos?)
   - Statistics oficiales sectoriales (ACEA, KBA, ANTS, etc.)

3. **Identificación cualitativa de gaps:**
   - "Me faltan dealers rurales del sur de Andalucía"
   - "Estoy subrepresentando los especialistas vehículos pesados"
   - "No tengo visibility del ecosistema dealer polaco que opera en DE fronterizo"

4. **Diseño de vector(es) nuevo(s):**
   - Brainstorming interno sobre qué fuente podría capturar ese gap
   - Investigación de fuentes específicas (blogs sectoriales regionales, directorios cerrados que puedan liberar, etc.)
   - Propuesta formal de nueva sub-técnica con base legal documentada

5. **Integración como sub-técnica:**
   - Módulo Go añadido a la familia existente o nueva familia P/Q/R si ortogonal
   - Test piloto sobre pequeña región
   - Medición delta aportado

6. **Re-ejecución del ciclo global:**
   - Si nueva sub-técnica aporta delta>0, se vuelve a Nivel 1 para esa nueva sub-técnica
   - Si Nivel 3 global se mantiene con la nueva integración, continuar sweep pleno

## Señales de falsa saturación

Casos a detectar para no concluir saturación erróneamente:

- **Familia caída:** una familia no ejecutó correctamente → health check bloquea ciclo.
- **Rate limit upstream:** una familia se quedó sin quota → marcar como "executed_partial", no contar para saturación.
- **Fuente cambiada:** endpoint alterado rompe parser → failing tests bloquean ciclo.
- **Data stale:** dataset open-data no actualizado desde hace >X meses → alerta operativa, posible source obsoleta.
- **Drift sistemático:** todos los ciclos encuentran "N nuevos dealers" donde N es ruido estadístico consistente sin variación → investigar si hay crawl loop o false positives consistentes.

## Documento de declaración de saturación

Cuando se alcanza Nivel 2/3/4 en un país:

1. Se genera documento `saturation_declaration_{country}_{level}_{date}.md` con:
   - Métricas exactas que justifican la declaración
   - Distribución final del knowledge graph para ese país
   - Cross-validation summary (overlap matrix)
   - Comparación con denominadores oficiales
   - Gaps identificados que se aceptan como estructurales (explicados)
   - Firma del operador aprobando

2. Sin declaración firmada no se transiciona a operación mantenimiento.

## Política de revisión

Cada 6 meses post-declaración de saturación, se ejecuta un **re-audit ciclo completo** para validar que la saturación se mantiene. Si delta>0 significativo en re-audit → regresión a discovery activo.

## No hay "100% alcanzado"

Bajo R4, la terminología del sistema NUNCA declara "100% alcanzado". Siempre declara "saturación de las N familias actuales". La diferencia no es semántica: refleja que siempre puede haber un vector aún no descubierto que capture un dealer aún invisible. El proceso es indefinidamente iterable y el sistema se diseña para absorber nuevos vectores sin refactorización.
