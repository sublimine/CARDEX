# ADR-0003 — Go sobre Python para el pipeline de ingestión y procesamiento

**Fecha**: 2026-04-27 (redacción retroactiva de decisión vigente)
**Estado**: Vigente
**Owner**: Salman Karrouch

---

## Contexto

CARDEX procesa listings de vehículos a través de un pipeline de consumers (Spider, Reaper, Indexer, classifier-bridge, gateway). Requisitos:
- Concurrencia robusta para scraping paralelo de múltiples fuentes.
- Footprint de memoria predecible bajo carga sostenida.
- Compilación a binario único sin dependencias de runtime para despliegue simple.
- Tipado estático para reducir clases de bugs en sistemas de larga ejecución.
- Latencia consistente sin pausas de garbage collector amplias.
- Cliente HTTP con control fino sobre fingerprint TLS (JA3 coherente, §22 CLAUDE.md).

## Opciones evaluadas

**Python (asyncio + httpx)**:
- Pros: ecosistema de scraping maduro (Scrapy, BeautifulSoup), iteración rápida.
- Contras: GIL limita paralelismo real, gestión de memoria menos predecible bajo carga prolongada, control de TLS fingerprint menos directo.

**Rust**:
- Pros: rendimiento superior, garantías de memoria.
- Contras: curva de aprendizaje, velocidad de iteración inferior para el equipo, ecosistema de scraping menos maduro que Go.

**Node.js (TypeScript)**:
- Pros: ecosistema de scraping moderno (Playwright, Puppeteer), familiaridad amplia.
- Contras: single-threaded por naturaleza, footprint de memoria superior, menos control sobre el cliente HTTP a nivel TLS.

**Go**:
- Pros: goroutines + channels para concurrencia natural, GC predecible, binario único, control directo sobre `net/http` y la pila TLS, librerías como `utls` para JA3 coherente, velocidad de compilación rápida.
- Contras: ecosistema de scraping menos amplio que Python, requiere más código boilerplate para parsing HTML.

## Decisión

Adoptar **Go 1.22** como lenguaje único del pipeline.

## Consecuencias aceptadas

- Todo nuevo consumer del pipeline se implementa en Go.
- Parsing HTML se gestiona con `goquery` o equivalentes; lo que falte respecto a Scrapy se construye internamente.
- Frontend permanece en React + Vite; backend de queries de cliente final puede coexistir en otro lenguaje si la diferencia operativa lo justifica.
- Patrones de concurrencia: toda goroutine con owner declarado, canal de cancelación, manejo de panic (CLAUDE.md §26).

## Fecha de revisión

No procede revisión sin justificación de migración mayor. ADR vigente indefinidamente.
