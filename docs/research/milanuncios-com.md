# milanuncios.com — TIER-1 (DataDome, behavioural stack required)

> Research date: 2026-06-03. Method: live `curl` probe with Chrome 130/136 UA from a datacenter egress (no proxy, no impersonation). Result: the cars surface answers with the "Pardon Our Interruption" challenge page — the canonical DataDome interstitial. milanuncios.com is therefore confirmed in the same WAF class as leboncoin.fr / lacentrale.fr and stays at Tier.T3.

---

## Verdict: TIER-1 (no Tier-0/Tier-1 implementation)

`milanuncios.com` is an Adevinta Spain marketplace (it absorbed Vibbo's classifieds business in 2019–2020 — see [vibbo-com.md](vibbo-com.md)). The homepage `/` answers 200 OK to a naked `curl` from any egress, but the moment we drill into the cars surface `/coches/` the response becomes the **DataDome challenge**: 405 status, `meta name="robots" content="noindex, nofollow"`, the body title "Pardon Our Interruption", and the embedded DataDome captcha bootloader (≥15 occurrences of `datadome` / `geo.captcha-delivery` in the body).

The CARDEX engine already classifies milanuncios at `Tier.T3, WAF.DATADOME` (`scrapers/engine/router/domain_map.py:81`); this research run **confirms** that classification end-to-end. No Tier-0/Tier-1 implementation will succeed against `/coches/`, `/coches-de-segunda-mano/`, or any search/listing path.

---

## Anti-bot stack [VERIFIED 2026-06-03]

### Homepage (decoy — passes without challenge)

```
$ curl -skIL https://www.milanuncios.com/
HTTP/1.1 200 OK
Server: nginx
Via: 1.1 …cloudfront.net (CloudFront)
X-Cache: Miss from cloudfront
…
```

CloudFront fronts an nginx origin; no DataDome marker on the body. This is the marketing/SEO surface and is intentionally kept reachable.

### Cars listing (the real target — challenged)

```
$ curl -skL -A "Mozilla/5.0 … Chrome/136" https://www.milanuncios.com/coches/
HTTP/1.1 405 Method Not Allowed
Content-Type: text/html

<!DOCTYPE html><html lang="es">
  <head>
    <meta charset="utf-8"/>
    <noscript><title>Pardon Our Interruption</title></noscript>
    <meta name="robots" content="noindex, nofollow"/>
    <meta http-equiv="cache-control" content="no-cache, no-store, must-revalidate"/>
    …
```

15+ matches for `datadome|dd-challenge|interstitial|captcha|geo.captcha-delivery` in the body confirm the interstitial. The `405` status is DataDome's standard "blocked-but-pretend-method-not-allowed" trick (same pattern as on leboncoin.fr).

### robots.txt is also challenged

```
$ curl -sk https://www.milanuncios.com/robots.txt
<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"/>
<noscript><title>Pardon Our Interruption</title></noscript>
…
```

So even the public discovery surface is blocked from datacenter egress — a Tier-1 sitemap-based approach is not viable either.

---

## Engine classification (already correct — keep as-is)

```python
PortalSpec("milanuncios.com", Tier.T3, WAF.DATADOME, countries=["ES"]),
```

T3 requires (per `domain_map.py` doctrine):
- Camoufox + Oxymouse behavioural stack
- CapSolver or equivalent for the DataDome captcha challenge
- Spanish-egress residential proxy fleet (DataDome scores datacenter IPs harshly; LATAM/EU-resi from Spanish IPs is the baseline)
- `trust_score >= 7.0` identity in the engine's premium pool (enforced by `BasePortalScraper._min_trust`)

---

## Action

- ✅ **Keep** the existing T3/DataDome entry in `domain_map.py` — no edit required.
- ❌ **No** `scrapers/portals/milanuncios_com/` module at Tier-0/Tier-1.
- When the engine's behavioural fleet is online for leboncoin.fr / lacentrale.fr, milanuncios.com follows the same surface: `/coches/`, `/coches-de-segunda-mano/<provincia>/`, with pagination via `pagina-N`. Reverse-engineer the search API after the captcha is solved (Adevinta uses similar internal `ms-mt--api-web.*.advgo.net` endpoints across markets; see `coches-net.md` for the analogous pattern).
