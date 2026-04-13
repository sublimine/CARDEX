# Plan de purga de código ilegal

## Estado: PENDIENTE
Auditoría detallada en task posterior.

## TODO
Para cada archivo identificado como ilegal en SPEC V6:
- [ ] ingestion/api_crawler/main.go
- [ ] ingestion/cartografo_headless.js
- [ ] ingestion/radar_vanguardia.js
- [ ] ingestion/h3_swarm_node.py (o variante en orchestrator/)

Por cada uno: existencia, líneas, resumen funcional, técnicas ilegales con número de línea, cobertura aportada, plan de reemplazo (referenciar E1-E12), recomendación.

Búsqueda de patrones adicionales en todo `ingestion/`: "user.agent", "User-Agent", "impersonate", "fingerprint", "scrapingbee", "residential", "JA3", "JA4", "stealth", "undetected".

Política: NO eliminar archivos en esta fase. Solo documentar.
