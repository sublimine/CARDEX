# coches.com — STAYS T2 (CF Pro, no bypass found)

> Research date: 2026-06-04. Method: WebSearch + bash curl probe. Result: coches.com returns 403 (blocked-by-allowlist) from datacenter egress. No public API, no sitemap access, no Next.js data routes. The site uses Adevinta Spain's custom `@s-ui/ssr` framework (NOT Next.js), so there are no `/_next/data/` routes to exploit. Stays at T2/CF_PRO.

---

## Verdict: STAYS T2 (no bypass, Camoufox required)

**IMPORTANT:** coches.com is distinct from coches.net. coches.net is already scraped (T1, `CochesNetScraper`). coches.com is a separate domain also under Adevinta Spain, but with Cloudflare Pro WAF active.

---

## Technical Stack [VERIFIED 2026-06-04]

- **Owner:** Adevinta Spain (same parent as Fotocasa, InfoJobs, Milanuncios)
- **Framework:** React SPA with custom `@s-ui/ssr` server-side rendering (NOT Next.js)
- **Build system:** `@s-ui/bundler` (Adevinta's proprietary config-free ES6 React bundler)
- **Component library:** `adevinta-spain-components` (open source, shared across Adevinta Spain properties)
- **No public API:** No documented JSON endpoints, no GraphQL, no `/_next/data/` routes
- **WAF:** Cloudflare Pro — returns `403 Forbidden` with `X-Proxy-Error: blocked-by-allowlist`

## Probing Results

```
$ curl -skIL "https://www.coches.com/"
HTTP/1.1 403 Forbidden
Content-Type: text/plain
X-Proxy-Error: blocked-by-allowlist
```

Even the root URL is blocked from datacenter egress. No robots.txt or sitemap.xml accessible.

## Third-Party Scrapers

Multiple Apify actors exist for coches.net (corpusculus/coches-net-actor, ivanvs/coches-net-scraper, kaidev/coches-net-scraper) — these parse HTML, confirming no clean JSON API exists. No dedicated scrapers for coches.com found.

---

## Engine Classification (unchanged)

```python
PortalSpec("coches.com", Tier.T2, WAF.CF_PRO, countries=["ES"])
```

---

## Action

- ❌ No `scrapers/portals/coches_com/` module
- Keep T2/CF_PRO classification
- When Camoufox is available, implement via HTML scraping (React SPA hydration)
