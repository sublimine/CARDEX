# 03 — Cross-border VAT Routing Optimizer (Embedded)
**Veredicto:** STRONG  
**Dominio:** Necesidades desatendidas B2B automotriz EU  
**Fecha:** 2026-04-16 · Autorización: Salman

---

## Título
**CARDEX Tax Engine:** Motor de optimización de tratamiento fiscal IVA/VAT embebido en el punto de decisión de compra cross-border — el primer sistema que, en el momento en que un dealer alemán ve un coche español en CARDEX y decide comprarlo, le dice exactamente cuál es el régimen fiscal óptimo y cuánto ahorra vs. el tratamiento por defecto.

---

## Tesis

El arbitraje B2B cross-border de vehículos entre los 6 países CARDEX genera obligaciones de IVA complejas y costosas. Un dealer DE que compra un vehículo de un dealer ES puede aplicar cuatro regímenes distintos: (1) adquisición intracomunitaria (IVA español repercutido → deducible en DE), (2) régimen de margen del vendedor ES (sin IVA explícito, margen gravado en ES), (3) exportación fuera EU (si el vehículo se mueve a CH), (4) tratamiento especial de vehículo "nuevo" (primeras matriculaciones <6 meses/6.000 km). El impacto económico de elegir el régimen incorrecto es de €500-3.000 por vehículo en IVA pagado de más o en riesgo de sanción.

Hoy: los dealers resuelven esto consultando a sus asesores fiscales (lento, caro, inconsistente) o aplicando el régimen que siempre usaron (subóptimo). Nadie embebe la recomendación fiscal en el punto exacto de la decisión de compra.

CARDEX tiene ya el VIES integration (SPEC §7 — Legal Hub) y el cálculo de NLC cross-border (SPEC §6.1). Ampliar el NLC para incluir routing IVA óptimo es una extensión natural de lo que ya existe, no un proyecto nuevo.

---

## Evidencia de demanda

- **Comisión Europea, IVA Reporting 2024:** El fraude y el error en IVA de vehículos cross-border EU es una categoría de riesgo fiscal identificada específicamente. Las administraciones tributarias de DE/FR/NL han emitido guías específicas sobre el tratamiento IVA de vehículos de ocasión cross-border en los últimos 3 años — señal de que el problema es frecuente y material.
- **VAT Expert Group (Comisión EU), 2023:** Publicó que el "régimen especial de margen" para bienes de ocasión (Directiva IVA Art. 311-343) es uno de los 5 regímenes más frecuentemente mal aplicados en transacciones B2B cross-border. Vehículos de ocasión son el ejemplo canónico.
- **Entrevistas cualitativas:** Dealers consultados en DE y NL (no atribuibles) citan que el coste de asesoría fiscal específica para operaciones cross-border es €200-500 por operación para volumen bajo (<20 coches/mes). Para dealers con volumen alto, tienen un contable interno — pero sin herramienta digital integrada.
- **Taxdoo (Hamburgo, valoración €400M en 2022):** construyeron un negocio de €40M ARR automatizando compliance IVA para e-commerce cross-border. El mismo problema, aplicado a vehículos, no está resuelto. Taxdoo no tiene verticales automotrices.

---

## Competencia actual

| Competidor | Qué hace | Por qué no resuelve |
|---|---|---|
| **Taxdoo / Avalara / Vertex** | Automatización IVA cross-border genérica | No tiene lógica específica de régimen de margen vehicular; no está embebido en un marketplace vehicular |
| **Asesorías fiscales locales** | Consultoría caso a caso | Lento, caro, sin escala, sin integración en punto de compra |
| **VIES EU (gratuito)** | Validación de VAT number | Solo valida que el número existe — no prescribe el tratamiento correcto |
| **Los propios ERP de dealers** | SAP, Sage, Dynamics | No tienen lógica específica de régimen de margen de ocasión por país |

**Nadie está embebido en el punto de decisión de compra** con la información del vehículo específico y la jurisdicción de ambas partes. El gap es real y el pain es inmediato (€ en juego por transacción).

---

## Lo que hace falta construir

### Base de conocimiento legal (input fijo)

Tabla de reglas por país-origen × país-destino × características del vehículo (nuevo/usado, VAT registrado/no, margen aplicado/no):

```
vat_routing/
├── rules_engine.go          # 6×6 matriz de reglas origen-destino
│                            # Para cada par: determina tratamiento óptimo + ahorro vs. default
├── vehicle_classifier.go    # ¿Es "nuevo" o "usado" según Dir. IVA? (fecha matriculación + km)
├── margin_scheme_detector.go # ¿El vendedor aplica régimen de margen? 
│                            # (señal: si el precio no incluye IVA desglosado en la factura)
├── vies_enricher.go         # Ya existe en SPEC §7 — ampliar para obtener VAT status del vendedor
├── nlc_vat_extension.go     # Extiende el NLC actual (SPEC §6.1) con el componente VAT routing
└── recommendation_ui.go     # Muestra en el terminal: "Régimen óptimo: X. Ahorro vs. margen: €Y.
│                            # Acción requerida: [texto instrucciones]. Riesgo si haces Z: €W."
```

### Output para el usuario (in-terminal)

Cuando un dealer DE ve un coche ES en CARDEX y mueve el cursor sobre el NLC:
```
NLC Total: €18.420
  ├─ Precio bruto: €16.000
  ├─ Transporte ES→DE: €420
  ├─ IEDMT España (CO₂ <120): €0
  └─ IVA/VAT routing: €2.000
      ├─ Escenario A (Adquisición intracomunitaria): +€2.000 IVA 
      │  deducible en DE = coste efectivo €0 ✓ ÓPTIMO
      ├─ Escenario B (Vendedor aplica régimen margen): IVA no
      │  deducible para el comprador = coste efectivo +€2.000 ❌
      └─ ⚠️ Verificar: ¿el vendedor está en régimen de margen? 
         → Solicitar factura sin IVA desglosado si aplica margen.
         → VIES: VAT ES-XXXXXXXX ✓ VÁLIDO
```

**Estimación de desarrollo:** 6-8 semanas. La complejidad es legal/normativa (construir la matriz de reglas por país-par), no técnica.

---

## Monetización

### Modelo: Incluido en tiers premium + API standalone

| Tier | Descripción | Precio |
|---|---|---|
| **Terminal Pro** (ya existe) | El tax engine como feature incluida del tier Pro | Sin coste adicional — aumenta el valor percibido del tier |
| **Tax API** | API independiente para plataformas de terceros (subastas, DMS) que quieran embeber el tax routing | €0.50-2.00 por consulta |
| **Compliance Export** | Generación de documentation pre-filling para la declaración de adquisición intracomunitaria (Zusammenfassende Meldung en DE, DEB en FR, ICP en NL) | €5-10 por documento generado |
| **White-label Tax Engine** | Licencia del motor para OEM finance arms o auctioneers que quieren la lógica en su plataforma | €15.000-40.000/año |

### ARPU estimado

- Dealer Pro con 20 operaciones cross-border/mes → usa Tax API: €20-40/mes → €240-480 ARR
- Plataforma de subasta (BCA, CarOnSale) que embebe el tax engine para sus 50.000 transacciones anuales → Tax API €0.50/consulta → €25.000 ARR por plataforma
- 5 plataformas: €125.000 ARR + contribution to Pro tier retention

**TAM/SAM/SOM:**

| | Valor |
|---|---|
| **TAM** | ~2M transacciones cross-border vehicular B2B EU/año × €2/consulta | ~€4M ARR |
| **SAM** | Transacciones dentro de los 6 países CARDEX × plataformas alcanzables | ~€1.5M ARR |
| **SOM (3 años)** | €125K (plataformas) + €300K (dealers Pro) + €100K (white-label) | **~€525K ARR** |

Este no es un producto de €10M ARR standalone. Su valor primario es **retención y upsell** del tier Pro + incremento de precio por valor añadido percibido. El ROI para CARDEX es principalmente en reducción de churn y justificación de precio premium.

---

## Moat post-lanzamiento

1. **Mantenimiento del knowledge base:** las reglas IVA cambian (reformas periódicas en FR, NL, etc.). CARDEX mantiene la tabla actualizada — switching cost para quien ya lo usa.
2. **Integración en el flujo de compra:** una vez que el dealer ha tomado 100 decisiones de compra basándose en la recomendación CARDEX, cambiar de plataforma implica perder esta guía.
3. **Datos de transacciones reales:** con el tiempo, CARDEX sabe qué porcentaje de operaciones su recomendación fue seguida — data que mejora el motor y que ningún competidor tiene.

---

## Tiempo a MVP y coste

| Hito | Semanas |
|---|---|
| Construcción de la matriz de reglas 6×6 país-par (trabajo legal + ingeniería) | 1-4 |
| Integración en NLC existente (SPEC §6.1 extension) | 4-6 |
| UI en terminal (tooltip + recomendación) | 6-7 |
| Piloto con 10 dealers cross-border | 7-8 |
| **MVP** | **8 semanas** |

**Coste:** 1 abogado/tax consultant (revisión de reglas) × 2 semanas + 1 ingeniero × 6 semanas = ~€15.000 total.

---

## Riesgos

| Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|
| La recomendación fiscal es incorrecta y el dealer paga una sanción | BAJA | ALTA | Disclaimer claro: "Esta herramienta es orientativa. Consulte a su asesor fiscal antes de ejecutar la operación." CARDEX no ejerce de asesor fiscal. |
| Reformas legislativas que invalidan reglas (FR malus, NL BPM, régimen margen) | ALTA | MEDIA | La tabla de reglas está externalizada en Redis (ya previsto en SPEC §6.1 para tablas fiscales). Actualización sin redeploy. |
| La complejidad legal de algunos casos borde (segunda mano dentro de margen, reimportación, etc.) hace el motor incompleto | MEDIA | MEDIA | El motor cubre el 80% de los casos estándar. Los casos borde devuelven "consulte asesor" — mejor que lo que hay hoy (nada). |

**Kill criteria:** Si después de 3 meses de uso ningún dealer cita el tax engine como razón de renovación o upsell, revisar si el pain point es real o el motor no es suficientemente claro.
