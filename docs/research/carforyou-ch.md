# carforyou.ch — DEAD DOMAIN (no implementation)

> Research date: 2026-06-03. Method: live `curl` probes (datacenter IP, naked Chrome 130 UA, no proxy). Conclusion: the host no longer serves a used-car marketplace.

---

## Verdict: SKIP

`carforyou.ch` and `www.carforyou.ch` both 301-redirect to `globalipaction.ch` — a WordPress site for an NGO (Global Initiative Against Transnational Organized Crime). There is **no automotive content** on the destination domain. The historical CarForYou used-car marketplace (Allegro / Naspers OLX portfolio) was shut down years ago and the domain repurposed.

---

## Evidence [VERIFIED 2026-06-03]

```
$ curl -skIL https://www.carforyou.ch/
HTTP/1.1 301 Moved Permanently
Server: Apache
Location: https://globalipaction.ch
…
HTTP/1.1 200 OK
Server: cloudflare
Link: <https://globalipaction.ch/wp-json/>; rel="https://api.w.org/", <https://globalipaction.ch/wp-json/wp/v2/pages/20>; rel="alternate"; title="JSON"; type="application/json"
```

Also confirmed:

```
$ curl -skI https://carforyou.ch/de/search
HTTP/1.1 301 Moved Permanently
Location: https://globalipaction.ch
```

Every probed path (`/`, `/de`, `/de/search`, `/aanbod`, `/cars`) redirects to the NGO root.

---

## Action

- **No scraper module.**
- **No domain_map entry.**
- This file exists so a future investigator does not re-research the same dead host.

If carforyou.ch is ever resurrected as a marketplace, replace this note with a fresh research pass against the real endpoints.
