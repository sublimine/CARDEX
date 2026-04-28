# ADR-0005 — Passive indexing: sitemap-first, sin ataque frontal a APIs

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

CARDEX debe indexar el 100% del territorio de listings de vehículos en 6 países UE. La estrategia de descubrimiento de listings determina:
- Coste técnico de la ingestión.
- Vida media antes de ban del proveedor.
- Cobertura efectiva alcanzable.
- Coherencia del fingerprint TLS (JA3).

## Opciones evaluadas

**Ataque frontal a API interna del proveedor**:
- Pros: datos estructurados directamente.
- Contras: APIs frecuentemente protegidas con tokens efímeros, rate-limit agresivo, detección de scraping inmediata, ban rápido. Coste de ingeniería sostenido para mantener el bypass. Superficie técnica frágil.

**Browser headless con stealth (Playwright + plugins anti-detección)**:
- Pros: ejecuta JavaScript completo, indistinguible de tráfico humano si está bien configurado.
- Contras: coste computacional alto, footprint de memoria amplio, dificultad de paralelización masiva, complejidad de mantener stealth ante actualizaciones de detectores.

**Sitemap-first (passive indexing)**:
- Pros: los sitemaps son superficie pública diseñada para indexación, cero detección porque el tráfico es legítimo, cobertura exhaustiva por construcción cuando el proveedor mantiene sitemap actualizado, throughput alto con cliente HTTP simple.
- Contras: depende de que el proveedor publique y mantenga sitemap. Sitemaps incompletos requieren combinación con paginación de listados públicos.

## Decisión

Adoptar **passive indexing con prioridad sitemap-first**:
- Para cada dominio nuevo: localizar sitemap (`/sitemap.xml`, `/robots.txt` referenciando sitemaps).
- Drenar el sitemap completo antes de considerar otras vías.
- Si el sitemap es incompleto: complementar con paginación de listados públicos vía deep links.
- Browsers con stealth solo para casos donde sitemap + paginación no alcanzan cobertura aceptable, y solo con stealth confirmado activo.
- Ataque frontal a APIs internas: prohibido como vía principal.

## Consecuencias aceptadas

- Paginación exhaustiva obligatoria: nunca abandonar un dominio antes de agotar su inventario completo (CLAUDE.md §27).
- Deep links obligatorios: URL directa al listing, root domains rechazados (CLAUDE.md §27).
- Coherencia JA3 mantenida sesión a sesión (ADR-0006 sobre TLS).
- La cobertura del 100% es alcanzable sin engañar al proveedor: usamos su superficie pública diseñada para ser indexada.

## Fecha de revisión

2026-10-27 o cuando un dominio crítico abandone su sitemap y la paginación pública no alcance cobertura aceptable.
