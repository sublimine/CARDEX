# 03_DISCOVERY_SYSTEM — Sistema de descubrimiento dealer 15-familias

## Propósito
Documentar exhaustivamente el sistema de descubrimiento del universo dealer B2B europeo en los seis países objetivo. Cada familia es un vector independiente de discovery con técnicas concretas, fuentes específicas, base legal, métricas y plan de implementación. La cross-fertilización entre familias construye el knowledge graph dealer que es la ventaja defensible de CARDEX.

## Principio rector
Multi-redundancia 360° (R5). Ningún dealer indexado por una sola familia. Mínimo tres vectores independientes para confianza alta. Iteración hasta saturación verificable (R4).

## Inventario de las 15 familias

| ID | Familia | Categoría | Cobertura esperada |
|---|---|---|---|
| A | Registros mercantiles federales y regionales | Legal-fiscal | Universo completo de empresas registradas con NACE 45.11 |
| B | Cartografía geográfica-comercial | Geo-comercial | POIs georreferenciados de actividad dealer |
| C | Cartografía web profunda (Common Crawl + alternativos) | Web-cartography | Sites con presencia web indexados por crawlers públicos |
| D | CMS + plugin fingerprinting | Tech-stack | Long-tail con WordPress/Joomla/Wix/Squarespace + plugins dealer |
| E | DMS hosted infrastructure mapping | Infra-DMS | Dealers cuya web es generada por su DMS provider |
| F | Aggregator dealer directories públicos | Marketplace-derived | Perfiles dealer en mobile.de/AutoScout24/etc. |
| G | Asociaciones sectoriales | Trade-association | Miembros de ZDK/CNPA/FACONAUTO/BOVAG/FEBIAC/AGVS |
| H | Redes oficiales OEM | OEM-network | Dealers oficiales VW/BMW/Mercedes/Stellantis/etc. |
| I | Redes de inspección y certificación | Inspection-network | TÜV/DEKRA/ITV/APK/CT stations + partner workshops |
| J | Capas regionales/cantonales/municipales | Sub-jurisdictional | 170 sub-jurisdicciones con registros locales |
| K | Buscadores alternativos open-source | Search-alt | SearXNG/YaCy/Brave/Marginalia queries programáticas |
| L | Plataformas sociales / business profiles públicos | Social | Google Maps/Facebook Pages/LinkedIn/Instagram |
| M | Validaciones fiscales y signals operativos | Fiscal-signals | VIES VAT + job boards + signals de actividad |
| N | Network/infrastructure intelligence | Infra-recon | Censys/Shodan/CT logs/passive DNS |
| O | Press digital, archivos históricos y prensa sectorial | Press-historical | Archivos de prensa automotriz por país |

## Estructura del directorio

```
03_DISCOVERY_SYSTEM/
├── README.md (este archivo)
├── families/
│   ├── README.md (índice de familias)
│   ├── A_registros_mercantiles.md
│   ├── B_geocartografia.md
│   ├── C_web_cartography.md
│   ├── D_cms_fingerprinting.md
│   ├── E_dms_hosted.md
│   ├── F_aggregator_directories.md
│   ├── G_asociaciones_sectoriales.md
│   ├── H_redes_oem.md
│   ├── I_redes_inspeccion.md
│   ├── J_subjurisdicciones.md
│   ├── K_buscadores_alternativos.md
│   ├── L_plataformas_sociales.md
│   ├── M_signals_fiscales.md
│   ├── N_infra_intelligence.md
│   └── O_prensa_historicos.md
├── KNOWLEDGE_GRAPH_SCHEMA.md
├── CROSS_FERTILIZATION.md
└── SATURATION_PROTOCOL.md
```

## Convención por archivo de familia

Cada familia se documenta con esta estructura:

1. **Identificador** (ID, nombre, categoría, fecha, estado)
2. **Propósito y rationale** (qué tipo de dealer captura, por qué es distinto)
3. **Sub-técnicas** (lista numerada, cada una con detalle)
4. **Fuentes concretas por país** (URLs, formatos, autenticación, rate limits)
5. **Base legal** (cobertura jurídica del acceso)
6. **Métricas** (qué se mide para evaluar efectividad)
7. **Implementación esperada** (módulos Go, dependencias, coste de cómputo)
8. **Cross-validation con otras familias** (qué overlap esperado, qué unique)
9. **Riesgos y mitigaciones**
10. **Iteración futura** (cómo se expande esta familia tras saturación)
