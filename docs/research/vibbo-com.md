# vibbo.com — REDIRECT TWIN (no implementation)

> Research date: 2026-06-03. Method: live `curl` probe. Conclusion: vibbo.com is a 301 alias of milanuncios.com (both Adevinta / Schibsted ES). There is no independent inventory.

---

## Verdict: SKIP (already covered by milanuncios.com)

Vibbo was the classifieds brand Adevinta retired in 2019–2020 after consolidating its Spanish second-hand marketplaces into Milanuncios. The vibbo.com host now 301-redirects every request — including the root — to `https://www.milanuncios.com/`. Scraping vibbo.com would only re-fetch the milanuncios inventory through one extra hop.

---

## Evidence [VERIFIED 2026-06-03]

```
$ curl -skIL https://www.vibbo.com/
HTTP/1.1 301 Moved Permanently
Server: AmazonS3
Location: https://www.milanuncios.com/
…
HTTP/1.1 200 OK     ← milanuncios.com response
Server: nginx
Via: 1.1 …cloudfront.net (CloudFront)
```

S3 static-site hosting + CloudFront — the classic Adevinta domain-retirement footprint.

---

## Anti-bot footprint at the target

Milanuncios.com is in front of DataDome (confirmed by hitting `/coches/` and receiving the "Pardon Our Interruption" interstitial). See [milanuncios-com.md](milanuncios-com.md) for the full WAF analysis and the reason it stays at Tier.T3 / behavioural-stack.

---

## Action

- **No `vibbo_com` scraper module.**
- **No standalone `domain_map.py` entry.** If we want vibbo.com soft-redirect coverage in the registry later, classify it as `Tier.T3, WAF.DATADOME` and point notes at milanuncios.
- Inventory coverage for vibbo's catalogue is delivered through the milanuncios.com scraper (when it is implemented at the behavioural tier).
