# Research: auto-api.ch — Swiss Vehicle Data Source (CARDEX)

> Investigation date: 2026-06-03. Method: DNS lookups, `curl_cffi` (`impersonate="chrome"`) live
> calls, WebSearch, WebFetch + raw-HTML inspection. Every fact tagged [VERIFIED] (observed live)
> or [ASSUMED] (docs/inference only).

## TL;DR / Headline

- **`auto-api.ch` DOES NOT EXIST.** [VERIFIED] The `.ch` domain returns **NXDOMAIN** from both the
  local resolver and Google `8.8.8.8`. No website, no API, nothing. Do not write code against it.
- The real, live service is **`auto-api.com`** (a `.com`). [VERIFIED] It is a **paid, sales-gated
  commercial scraping-as-a-service** product, not an open/free API.
- **`auto-api.com` does NOT advertise AutoScout24 Switzerland coverage.** [VERIFIED from raw HTML]
  Its AutoScout24 markets are listed as "Germany, Italy, France, Spain, Netherlands, Belgium,
  Austria, and other European countries." Zero mentions of "Switzerland", "Swiss", or ".ch".
- The genuine Swiss upstream is **`autoscout24.ch`**, which is **live and behind Cloudflare**.
  [VERIFIED]

---

## 1. What is auto-api.ch?

| Question | Answer | Confidence |
|---|---|---|
| Does `auto-api.ch` resolve? | **No — NXDOMAIN** | [VERIFIED] |
| Is it a public/open REST API? | N/A — domain does not exist | [VERIFIED] |
| Most likely intended target | `auto-api.com` (paid scraper SaaS) | [VERIFIED it's live] / [ASSUMED it's what was meant] |

### Evidence — DNS (NXDOMAIN)

```
$ nslookup auto-api.ch
*** internetbox.home no encuentra auto-api.ch: Non-existent domain

$ nslookup auto-api.ch 8.8.8.8
*** dns.google no encuentra auto-api.ch: Non-existent domain
```

```
# curl_cffi, impersonate=chrome
auto-api.ch     -> ERR DNSError curl:(6) Could not resolve host: auto-api.ch
www.auto-api.ch -> ERR DNSError curl:(6) Could not resolve host: www.auto-api.ch
api.auto-api.ch -> ERR DNSError curl:(6) Could not resolve host: api.auto-api.ch
```

There is no DNS record at all — this is not a firewall block or geo-block; the name is unregistered
in the `.ch` zone (or has no nameservers). A WebSearch for "auto-api.ch ..." surfaces only
`auto-api.com`.

---

## 2. The actual service: auto-api.com

### What it is [VERIFIED]

`curl_cffi` GET `https://auto-api.com/` → **HTTP 200**, `server: nginx`, `cf-ray: None` (no
Cloudflare on the marketing site). It is a Next.js marketing site. `<title>`:

```
Car Listings API, Automotive Data Scraper | AUTO-API.COM
```

Meta description (verbatim):

> "Car Listings API for Encar, Mobile.de, AutoScout24, Che168, Dubizzle, Dongchedi. Professional
> automotive scraper with real-time monitoring and daily data exports."

So it is a **reseller of scraped marketplace data**, sold as an API + daily exports. Sources:
Encar (KR), Mobile.de (DE), AutoScout24 (EU network), Che168 / Dongchedi (CN), Dubizzle (AE).

### Is it open / paid / website?

**Paid, sales-gated.** [VERIFIED from raw HTML JSON-LD]:

```json
"offers":{"@type":"Offer","price":"Contact for pricing","priceCurrency":"USD"}
```

No public pricing, no free tier, no self-serve signup observed. The docs page says access is via a
**"Get API Access"** button → contact page, contact `access@auto-api.com` / Telegram, with a claim
of "Access provided within 2 minutes." [VERIFIED page text].

---

## 3. Documented API contract (auto-api.com AutoScout24)

> Source: `https://auto-api.com/autoscout24`. The base URL, auth param, and endpoint paths below
> were extracted from the **raw rendered HTML** (verbatim `<code>` blocks), not just a model
> summary. They are [VERIFIED as documented] but **[ASSUMED for runtime behavior]** — I could not
> execute them (no tenant subdomain / key; see §4).

### Base URL [VERIFIED in HTML]

```
https://{access_name}.auto-api.com/api/v2/autoscout24
```

`{access_name}` is a **per-tenant subdomain** issued on purchase. The apex host does NOT serve the
API (see §4 evidence).

### Auth [VERIFIED in HTML]

- API key passed as the **`api_key` query parameter**. Verbatim from HTML:
  `<code>api_key</code> parameter`.
- No key = no access. This is a credentialed, paid API.

### Endpoints [VERIFIED as documented]

| Method | Path | Purpose | Key params |
|---|---|---|---|
| GET | `/filters` | Available filter option values | `api_key` |
| GET | `/offers` | **Paginated listing search** (main listings endpoint) | `api_key`, `page` (required), `mark`, `model`, `configuration`, `transmission_type`, `color`, `body_type`, `engine_type`, `year_from/to`, `km_age_from/to`, `price_from/to` (EUR), `country` |
| GET | `/offer` | Single listing detail | `api_key`, `inner_id` (UUID) |
| GET | `/change_id` | Starting change-id for a date | `api_key`, `date=YYYY-MM-DD` |
| GET | `/changes` | Delta feed (new/changed/removed) | `api_key`, `change_id` |

Example (verbatim from HTML):

```
https://{access_name}.auto-api.com/api/v2/autoscout24/change_id?api_key=YOUR_API_KEY&date=2025-01-15
```

Docs note (verbatim): "For search functionality, leverage /offers with filter and pagination
parameters (make, model, price, year, country)".

### Response shape [ASSUMED — from docs summary, not executed]

JSON. Listing object fields (per docs): `id`, `inner_id`, `url`, `mark`, `model`, `configuration`,
`complectation`, `year`, `color`, `price_eur`, `km_age`, `engine_type`, `transmission_type`,
`body_type`, `address`, `seller_type`, `is_dealer`, `description`, `displacement`, `horse_power`,
`first_registration`, `images`.

Mapping for CARDEX:
- **listing URL** → `url`
- **stable ID** → `inner_id` (UUID; used by `/offer` and the changes feed) — secondary `id`
- **make** → `mark`
- **model** → `model`
- **year** → `year` (also `first_registration`)
- **price** → `price_eur` (EUR)

### Pagination [ASSUMED — from docs summary]

Page-number based. `page` is a required `/offers` param. Response carries:

```json
"meta": { "page": 1, "next_page": 2, "limit": 20 }
```

Iterate `page` until `next_page` is null. For incremental sync, use `/change_id?date=` → seed →
poll `/changes?change_id=`.

### SDKs [VERIFIED in HTML]

Official client libs advertised for PHP, Node.js, Python, Go, C#, Java, Ruby, Rust.

---

## 4. Auth & reachability — why I could not execute it

The API is NOT on the apex; it requires a provisioned `{access_name}` subdomain + `api_key`.
I have neither, so **no live API response could be captured.** [VERIFIED — the gating itself]:

```
# Apex path returns the Next.js 404 MARKETING page, not a real API error:
GET https://auto-api.com/api/v2/autoscout24/offers?page=1   -> 404  CT text/html  (Next.js HTML)
GET https://auto-api.com/api/v2/autoscout24/filters         -> 404  CT text/html  (Next.js HTML)
GET https://auto-api.com/api/v2/autoscout24                 -> 404  text/html

# Guessed tenant/api subdomains do not resolve:
api.auto-api.com   -> DNSError (NXDOMAIN)
demo.auto-api.com  -> DNSError (NXDOMAIN)

# No public docs/openapi surface:
/api /docs /api/docs /swagger /openapi.json  -> all 404 (Next.js HTML)
```

**Honest conclusion:** the `/offers` contract above is the *documented* shape only. I have NOT seen a
single live JSON row from this API and cannot without a paid key. Treat field names as
[ASSUMED] until validated against a real tenant response.

---

## 5. The real Swiss source: autoscout24.ch [VERIFIED]

Since auto-api.com does not cover Switzerland, the genuine upstream for Swiss listings is
`autoscout24.ch` (operated by RingierAutoScout24 — a distinct entity from the pan-European
AutoScout24 network that auto-api.com scrapes).

### Live probe [VERIFIED]

```
GET https://www.autoscout24.ch/de
  STATUS 200 | server: cloudflare | content-type: text/html
  cf-ray present, cf-cache-status present
  set-cookie: route=...; (Cloudflare edge)
```

### Anti-bot [VERIFIED: Cloudflare present]

- `server: cloudflare` and `cf-ray` on every response → **Cloudflare fronts the site.**
- A naive guessed JSON path (`/de/hci/v1/search`) returned 404 (Cloudflare HTML), so the internal
  search/JSON API path was NOT confirmed in this pass. [ASSUMED] AS24.ch is a Next.js SPA that
  almost certainly calls an internal JSON/GraphQL search endpoint discoverable via browser DevTools
  / Playwright network capture — that discovery is the natural next research step.
- The 200 on `/de` with `impersonate="chrome"` suggests Cloudflare is not currently throwing a hard
  interactive challenge for a single TLS-fingerprinted request, but rate/behavioral challenges under
  scale are likely. [ASSUMED].

---

## 6. Recommended scraper strategy (CARDEX tiers)

**Tier definition:** T0 = official/contracted API; T1 = undocumented internal JSON/XHR API;
T2 = HTML parse; T3 = headless browser / heavy anti-bot evasion.

### Recommendation

1. **Do not target `auto-api.ch`** — it does not exist. Dead end.

2. **auto-api.com is a T0-style paid API, but WRONG GEOGRAPHY for CARDEX.** It does not list Swiss
   coverage. Only pursue if (a) Swiss data is genuinely out of scope and you need the broader EU
   network, or (b) sales explicitly confirms autoscout24.ch is included. **Action:** email
   `access@auto-api.com` and ask, verbatim: "Do you provide AutoScout24 **Switzerland**
   (autoscout24.ch) listings, and at what price?" Until confirmed, assume **NO**.

3. **For Swiss listings, the real target is `autoscout24.ch` directly:**
   - **T1 (preferred):** Reverse-engineer its internal search JSON/GraphQL endpoint via Playwright
     network capture, then replay with `curl_cffi impersonate="chrome"`. Cloudflare is present but
     did not hard-block a single fingerprinted GET. This is the highest-ROI path and the natural
     next research task.
   - **T3 (fallback):** Full headless browser (Playwright) with the `playwright` MCP / stealth if
     Cloudflare escalates to behavioral challenges at scale.
   - Avoid T2 HTML scraping unless the JSON API proves inaccessible — SPA HTML is brittle.

### Bottom line

The single best *Swiss* path is **T1 against autoscout24.ch's internal API** (discover endpoint
first). The paid auto-api.com API is a clean T0 contract but **does not cover Switzerland as
documented**, so it is not a fit for CARDEX Swiss listings without written confirmation from their
sales.

---

## Appendix — Confidence ledger

| Fact | Status |
|---|---|
| `auto-api.ch` is NXDOMAIN (does not exist) | [VERIFIED] |
| `auto-api.com` live, nginx, no Cloudflare, paid scraper SaaS | [VERIFIED] |
| auto-api.com base URL `{access_name}.auto-api.com/api/v2/autoscout24` | [VERIFIED in HTML] |
| auth = `api_key` query param | [VERIFIED in HTML] |
| endpoint paths `/offers /offer /filters /change_id /changes` | [VERIFIED as documented in HTML] |
| `/offers` runtime behavior, JSON field names, `meta` pagination | [ASSUMED — never executed, no key] |
| auto-api.com pricing = "Contact for pricing" USD, no free tier | [VERIFIED in JSON-LD] |
| auto-api.com does NOT list Switzerland coverage | [VERIFIED — 0 hits in raw HTML] |
| autoscout24.ch live + behind Cloudflare | [VERIFIED] |
| autoscout24.ch internal JSON search endpoint path | [ASSUMED — not yet discovered] |
