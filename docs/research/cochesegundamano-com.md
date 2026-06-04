# cochesegundamano.com — DEAD DOMAIN (no implementation)

> Research date: 2026-06-03. Method: live `curl` probe (datacenter IP, naked Chrome 130 UA, no proxy). Conclusion: domain is parked.

---

## Verdict: SKIP

`cochesegundamano.com` is a parked domain. The host returns `Server: Parking/1.0` and a 405 Method Not Allowed for every method we tried, including GET. There is no marketplace content to scrape.

---

## Evidence [VERIFIED 2026-06-03]

```
$ curl -skIL https://www.cochesegundamano.com/
HTTP/1.1 405 Method Not Allowed
Content-Length: 556
Content-Type: text/html
Server: Parking/1.0
```

`Server: Parking/1.0` is a registrar parking-page server (the same banner Sedo/GoDaddy parking servers expose); the `405` on `GET` is the typical signal that the domain has no application backend at all — the parking provider only answers to `OPTIONS`/`HEAD` for indexing purposes.

---

## Action

- **No scraper module.**
- **No domain_map entry.**
- Keep this note so a future investigator does not waste a research cycle.

If the domain is ever sold to a new operator running a real used-car marketplace, replace this file with a fresh research pass against the live endpoints.
