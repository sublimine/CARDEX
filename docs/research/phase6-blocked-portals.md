# Phase 6 — Blocked, Dead & Non-Viable Portals

> Research date: 2026-06-04 | Branch: `phase6-es-nl`
>
> This document catalogues every portal evaluated for Phase 6 (ES/NL expansion)
> that cannot be scraped, is dead, or is otherwise excluded from implementation.
> Portals that *are* being implemented (ocasionplus.com, autokopen.nl,
> nederlandmobiel.nl, viabovag.nl, autolina.ch, anibis.ch) are documented in
> their own scraper READMEs.

---

## Summary Table

| #  | Domain                  | Country | Status       | WAF / Blocker      | Tier | Est. Listings | Reason                                      |
|----|-------------------------|---------|--------------|--------------------|------|---------------|----------------------------------------------|
| 1  | wallapop.com            | ES      | BLOCKED      | PerimeterX         | T2   | ~500k+        | PerimeterX blocks all automated requests     |
| 2  | milanuncios.com         | ES      | BLOCKED      | DataDome           | T3   | ~200k+        | DataDome JS challenge + device fingerprinting|
| 3  | coches.com              | ES      | BLOCKED      | Cloudflare Pro     | T2   | ~196k         | CF Pro with JS challenge                     |
| 4  | vibbo.com               | ES      | DEAD         | N/A                | --   | 0             | Redirects to milanuncios.com                 |
| 5  | cochesegundamano.com    | ES      | DEAD         | N/A                | --   | 0             | Domain parked/expired                        |
| 6  | segundamano.es          | ES      | DEAD         | N/A                | --   | 0             | Redirects to vibbo.com -> milanuncios.com    |
| 7  | flexicar.es             | ES      | NEEDS_PROBE  | Unknown            | T1?  | ~25k+         | Dealer chain, couldn't probe from sandbox    |
| 8  | clicars.com             | ES      | NEEDS_PROBE  | Unknown            | T1?  | Unknown       | Online dealer platform, needs investigation  |
| 9  | swipcar.com             | ES      | NEEDS_PROBE  | Unknown            | T1?  | Unknown       | Car aggregator, needs investigation          |
| 10 | carwow.es               | ES      | NEEDS_PROBE  | Unknown            | T1?  | Unknown       | UK-based car buying service in Spain         |
| 11 | km77.com                | ES      | SKIP         | N/A                | --   | N/A           | News/review site, not a marketplace          |
| 12 | pistonudos.com          | ES      | SKIP         | N/A                | --   | N/A           | Automotive news site                         |
| 13 | autobild.es             | ES      | SKIP         | N/A                | --   | N/A           | News site (some listings section)            |
| 14 | motorflash.com          | ES      | SKIP         | N/A                | --   | N/A           | Dealer management software, not consumer     |
| 15 | sumauto.com             | ES      | SKIP         | N/A                | --   | N/A           | Parent company, not a portal                 |
| 16 | autonocion.com          | ES      | SKIP         | N/A                | --   | N/A           | Automotive news site                         |
| 17 | trovit.es/coches        | ES      | SKIP         | N/A                | --   | N/A           | Meta-search aggregator, no own inventory     |
| 18 | autoweek.nl             | NL      | BLOCKED      | Akamai V3          | T2   | Unknown       | Akamai V3 WAF on classifieds section         |
| 19 | autowereld.nl           | NL      | NEEDS_PROBE  | Unknown (bot det?) | T1?  | ~300k+        | Empty response on probe, possible geo-block  |
| 20 | autotrader.nl           | NL      | SKIP         | N/A                | --   | N/A           | IS AutoScout24 NL rebrand (already covered)  |
| 21 | anwb.nl/auto/occasions  | NL      | SKIP         | N/A                | --   | N/A           | Aggregator, no own inventory                 |
| 22 | spoticar.nl             | NL      | NEEDS_PROBE  | Unknown            | T1?  | Small         | Stellantis certified used cars               |

---

## SPAIN -- BLOCKED

### 1. wallapop.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | wallapop.com                                                          |
| **Country**      | ES                                                                    |
| **Status**       | BLOCKED                                                               |
| **WAF**          | PerimeterX                                                            |
| **Tier**         | T2 (would need T3 with behavioral emulation)                          |
| **Listings**     | ~500k+ in Spain                                                       |
| **Tech stack**   | PerimeterX bot detection, JS fingerprinting, behavioral analysis      |
| **domain_map**   | Already registered as `T2/PERIMETER_X`                                |

**Description:** Major C2C marketplace in Spain, similar to Craigslist/Marktplaats. Wide
category range (not auto-only). PerimeterX blocks all automated requests including
`curl_cffi` with browser impersonation. Even `web_fetch` with headers gets blocked.

**Why blocked:** PerimeterX is among the hardest WAFs to bypass. It requires:
- Camoufox with full browser fingerprint consistency
- Behavioral emulation (mouse movements, scroll patterns) via Oxymouse
- Residential proxy rotation
- Possibly CapSolver for challenge pages

**Next steps:** Defer to T3 implementation phase. Would need Camoufox + Oxymouse
behavioral pipeline. ROI is high given listing volume but engineering cost is significant.

---

### 2. milanuncios.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | milanuncios.com                                                       |
| **Country**      | ES                                                                    |
| **Status**       | BLOCKED                                                               |
| **WAF**          | DataDome                                                              |
| **Tier**         | T3                                                                    |
| **Listings**     | ~200k+ auto listings                                                  |
| **Tech stack**   | DataDome JS challenge, device fingerprinting, behavioral analysis     |
| **domain_map**   | Already registered as `T3/DATADOME`                                   |

**Description:** Major Spanish classifieds site (formerly Segundamano). Large auto
section. DataDome is one of the most aggressive bot detection systems, using JS
challenges combined with device fingerprinting.

**Why blocked:** DataDome requires:
- Full browser execution (Camoufox)
- Residential proxies (datacenter IPs are immediately flagged)
- Behavioral emulation
- CapSolver integration for interstitial challenges

**Next steps:** Defer to T3 implementation phase alongside leboncoin.fr and
lacentrale.fr (same WAF vendor). Shared DataDome bypass infrastructure would cover
all three portals.

---

### 3. coches.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | coches.com                                                            |
| **Country**      | ES                                                                    |
| **Status**       | BLOCKED                                                               |
| **WAF**          | Cloudflare Pro                                                        |
| **Tier**         | T2                                                                    |
| **Listings**     | ~196k                                                                 |
| **Tech stack**   | Cloudflare Pro with JS challenge, part of Sumauto group               |
| **domain_map**   | Already registered as `T2/CF_PRO`                                     |

**Description:** Part of the Sumauto group (same parent as coches.net). Uses Cloudflare
Pro with active JS challenges. Unlike coches.net (which is T1/NONE and implementable),
coches.com has stricter protection.

**Why blocked:** CF Pro JS challenge requires browser execution. Could potentially be
solved with Camoufox + storageState approach, but lower priority than other T2 targets
given coches.net already covers the Sumauto inventory overlap.

**Next steps:** Evaluate after coches.net scraper is stable. Much of the inventory
overlaps with coches.net, so incremental value is lower than listing count suggests.

---

## SPAIN -- DEAD PORTALS

### 4. vibbo.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | vibbo.com                                                             |
| **Country**      | ES                                                                    |
| **Status**       | DEAD                                                                  |

**Description:** Was the rebrand of Segundamano. Domain now 301-redirects to
milanuncios.com. No independent inventory or scraping target remains.

**Conclusion:** Permanently dead. Do not implement. Remove from any target lists.

---

### 5. cochesegundamano.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | cochesegundamano.com                                                  |
| **Country**      | ES                                                                    |
| **Status**       | DEAD                                                                  |

**Description:** Domain is parked or expired. No active content. Was likely an
auto-specific offshoot of Segundamano/vibbo ecosystem.

**Conclusion:** Permanently dead. Do not implement.

---

### 6. segundamano.es

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | segundamano.es                                                        |
| **Country**      | ES                                                                    |
| **Status**       | DEAD                                                                  |

**Description:** Original classifieds brand. Redirect chain:
`segundamano.es` -> `vibbo.com` -> `milanuncios.com`. The brand was acquired and
folded into Adevinta's milanuncios.com.

**Conclusion:** Permanently dead. The entire Segundamano brand has been absorbed
into milanuncios.com.

---

## SPAIN -- NEEDS_PROBE

### 7. flexicar.es

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | flexicar.es                                                           |
| **Country**      | ES                                                                    |
| **Status**       | NEEDS_PROBE                                                           |
| **WAF**          | Unknown                                                               |
| **Tier**         | Unknown (estimated T1)                                                |
| **Listings**     | ~25k+ vehicles                                                        |
| **Tech stack**   | Unknown -- likely has API, 180+ dealerships across Spain              |

**Description:** Large Spanish dealer chain with 180+ physical dealerships. Significant
used car inventory (~25k+ vehicles). Could not probe tech stack from sandbox
environment.

**Next steps:** Probe from local environment or NL/ES egress:
1. `curl -sI https://flexicar.es` -- check WAF headers
2. Check for Next.js/React hydration in page source
3. Look for XHR/fetch API calls in browser DevTools
4. Check for sitemap.xml or robots.txt API hints

---

### 8. clicars.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | clicars.com                                                           |
| **Country**      | ES                                                                    |
| **Status**       | NEEDS_PROBE                                                           |
| **WAF**          | Unknown                                                               |
| **Tier**         | Unknown (estimated T1)                                                |
| **Listings**     | Unknown                                                               |
| **Tech stack**   | Unknown -- online dealer platform                                     |

**Description:** Online car dealer platform in Spain. Buy/sell used cars online with
delivery. Similar model to Cazoo/Carvana.

**Next steps:** Same probe methodology as flexicar.es.

---

### 9. swipcar.com

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | swipcar.com                                                           |
| **Country**      | ES                                                                    |
| **Status**       | NEEDS_PROBE                                                           |
| **WAF**          | Unknown                                                               |
| **Tier**         | Unknown                                                               |
| **Listings**     | Unknown                                                               |
| **Tech stack**   | Unknown -- car aggregator                                             |

**Description:** Spanish car aggregator platform. Needs investigation for tech stack,
WAF, and listing volume.

**Next steps:** Same probe methodology as flexicar.es.

---

### 10. carwow.es

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | carwow.es                                                             |
| **Country**      | ES                                                                    |
| **Status**       | NEEDS_PROBE                                                           |
| **WAF**          | Unknown                                                               |
| **Tier**         | Unknown                                                               |
| **Listings**     | Unknown                                                               |
| **Tech stack**   | Unknown -- UK-based car buying service expanded to Spain              |

**Description:** Carwow is a UK-based car buying/comparison service that expanded to
several European markets including Spain. Primarily a new-car configurator/comparison
tool, but also has used car listings.

**Next steps:** Probe tech stack. May have limited used car inventory since their
core business is new car comparison.

---

## SPAIN -- SKIP (Not Car Marketplaces)

### 11. km77.com

**Category:** Automotive news/review site.
**Why skipped:** Editorial content only. Not a marketplace with scrapeable vehicle
listings. Reviews, specifications, and comparison tools -- no inventory.

### 12. pistonudos.com

**Category:** Automotive news site.
**Why skipped:** News and editorial content only. No vehicle marketplace or inventory.

### 13. autobild.es

**Category:** News site with minor listings section.
**Why skipped:** Primarily automotive journalism. Has a small listings section but
listings are aggregated from other portals (not own inventory). Not worth implementing.

### 14. motorflash.com

**Category:** Dealer management/aggregation software.
**Why skipped:** B2B SaaS product for dealers to manage and distribute their inventory
to consumer-facing portals. Not a consumer-facing marketplace. Dealers push listings
FROM motorflash TO portals like coches.net.

### 15. sumauto.com

**Category:** Parent company website.
**Why skipped:** Corporate site for the Sumauto group which owns coches.net, motor.es,
and autocasion.com. Not a portal itself. Child portals are already in scope.

### 16. autonocion.com

**Category:** Automotive news site.
**Why skipped:** News, reviews, and automotive journalism. No marketplace functionality.

### 17. trovit.es/coches

**Category:** Meta-search aggregator.
**Why skipped:** Aggregates listings from multiple portals and redirects users to the
source portal. Has no own inventory. Scraping trovit would yield duplicate data already
available from source portals (coches.net, autocasion.com, etc.).

---

## NETHERLANDS -- BLOCKED

### 18. autoweek.nl

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | autoweek.nl                                                           |
| **Country**      | NL                                                                    |
| **Status**       | BLOCKED                                                               |
| **WAF**          | Akamai V3                                                             |
| **Tier**         | T2                                                                    |
| **Listings**     | Unknown (media site + classifieds section)                            |
| **Tech stack**   | Akamai Bot Manager V3                                                 |

**Description:** Dutch automotive media brand with a classifieds section. Akamai V3 is
the same WAF that protects mobile.de and AutoScout24 -- requires browser-based approach
with `_abck` cookie management.

**Why blocked:** Akamai V3 requires Camoufox + storageState + `_abck` cookie rotation.
Same infrastructure as mobile.de/AutoScout24 T2 pipeline.

**Next steps:** Could be added when Akamai V3 T2 pipeline is production-stable.
Lower priority than mobile.de/AutoScout24 given smaller inventory.

---

### 19. autowereld.nl

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | autowereld.nl                                                         |
| **Country**      | NL                                                                    |
| **Status**       | NEEDS_PROBE                                                           |
| **WAF**          | Unknown (empty response on web_fetch)                                 |
| **Tier**         | T1 (estimated)                                                        |
| **Listings**     | ~300k+ (historically)                                                 |
| **Tech stack**   | Has/had REST API (deprecated), possible bot detection or geo-blocking |

**Description:** Major Dutch car classifieds portal with historically 300k+ listings.
Probe via `web_fetch` returned an empty response -- could indicate bot detection,
geo-blocking (Netherlands-only egress required), or server-side filtering.

**Why blocked:** Cannot determine tech stack or WAF from current probe environment.
Empty response could mean anything from simple geo-fence to aggressive bot detection.

**Next steps:**
1. Probe from NL egress IP (residential or NL datacenter)
2. Check if deprecated API still responds
3. Browser-based inspection of response headers and JS challenges
4. If geo-blocked, may be trivially accessible with NL proxy

---

## NETHERLANDS -- SKIP

### 20. autotrader.nl

**Category:** AutoScout24 NL rebrand.
**Why skipped:** autotrader.nl IS AutoScout24 Netherlands. Evidence:
- Vehicle images served from `prod.pictures.autoscout24.net`
- Dealer cockpit links to `autoscout24.nl/cockpit`
- Same underlying inventory and API

**Already covered by:** `autoscout24.*` scraper in domain_map (T2/AKAMAI_V3).
Implementing autotrader.nl separately would produce 100% duplicate data.

### 21. anwb.nl/auto/occasions

**Category:** Aggregator.
**Why skipped:** ANWB (Dutch automobile association) occasions page aggregates listings
from viabovag.nl and other partner portals. Links out to source portals for actual
purchase. No own inventory. viabovag.nl is already being implemented in Phase 6.

### 22. spoticar.nl

| Field            | Value                                                                 |
|------------------|-----------------------------------------------------------------------|
| **Domain**       | spoticar.nl                                                           |
| **Country**      | NL                                                                    |
| **Status**       | NEEDS_PROBE                                                           |
| **WAF**          | Unknown                                                               |
| **Tier**         | Unknown                                                               |
| **Listings**     | Small (Stellantis certified only)                                     |
| **Tech stack**   | Unknown -- PSA Group (Stellantis) certified used car platform         |

**Description:** Stellantis (Peugeot/Citroen/Opel/Fiat) certified used car platform
for the Netherlands. Likely small inventory limited to Stellantis brands only.

**Next steps:** Low priority given limited brand coverage and small inventory. Probe
only if broader NL coverage is needed after primary portals are stable.

---

## Appendix: Probe Methodology

For all NEEDS_PROBE portals, the standard investigation process is:

```bash
# 1. Check response headers and WAF signatures
curl -sI https://<domain>/ | head -30

# 2. Check for common WAF cookies/headers
curl -s https://<domain>/ -D- -o /dev/null | grep -iE '(server|x-powered|cf-ray|akamai|datadome|set-cookie)'

# 3. Look for API/XHR endpoints in page source
curl -s https://<domain>/ | grep -oP '(api|_next|graphql|/v[0-9]+/)[^"'"'"']*' | head -20

# 4. Check sitemap and robots
curl -s https://<domain>/sitemap.xml | head -20
curl -s https://<domain>/robots.txt | head -30

# 5. Browser DevTools network tab for XHR calls during search
```

Probes should be run from an appropriate egress point (NL IP for Dutch portals,
ES IP for Spanish portals) to avoid geo-blocking false positives.
