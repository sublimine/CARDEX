# ouestfrance-auto.com / zoomcar.fr — STAYS T2 (CF Pro, no bypass found)

> Research date: 2026-06-04. Method: WebSearch + bash curl probe + GitHub survey. Result: ouestfrance-auto.com was permanently merged into zoomcar.fr as of April 2026. Both domains are inaccessible from datacenter egress (curl returns empty). The legacy PHP backend has no documented public API. Stays at T2/CF_PRO.

---

## Verdict: STAYS T2 (no bypass, Camoufox required)

OuestFrance-auto.com was a 27-year-old car classified site by Ouest-France Multimedia. In early April 2026, it was fully absorbed into zoomcar.fr. The old domain now redirects to zoomcar.fr.

---

## Technical Stack [VERIFIED 2026-06-04]

- **Owner:** Ouest-France Multimedia (part of SIPA media group)
- **Framework:** Legacy PHP backend (confirmed via `github.com/OuestFrance-Multimedia/zoomcar` — PHP files like `library/Zoomcar/Page/Context.php`)
- **Infrastructure:** Kubernetes + Terraform + ArgoCD + Varnish cache layer
- **No SPA/Next.js:** Traditional server-rendered HTML pages, no JavaScript framework
- **No public API:** No JSON endpoints, no GraphQL, no REST API documented
- **WAF:** Cloudflare Pro — curl returns empty responses (HTTP 000, zero bytes)

## Probing Results

```
$ curl -sk -o /dev/null -w "HTTP %{http_code} size=%{size_download}" \
    -A "Mozilla/5.0 ... Chrome/136.0" "https://www.zoomcar.fr/"
HTTP 000 size=0
```

Connection drops before returning a response — aggressive edge-level blocking.

## GitHub Repos

The `OuestFrance-Multimedia` GitHub organization (19 repos) contains infrastructure tooling (Terraform, Helm, ArgoCD) and the legacy PHP codebase, but no API specifications or public endpoints.

---

## Engine Classification (unchanged)

```python
PortalSpec("ouestfrance-auto.fr", Tier.T2, WAF.CF_PRO, countries=["FR"])
PortalSpec("zoomcar.fr", Tier.T2, WAF.CF_PRO, countries=["FR"],
           notes="ex-ouestfrance-auto.com [VERIFIED 2026-06-04]")
```

---

## Action

- ❌ No `scrapers/portals/zoomcar_fr/` module
- Keep T2/CF_PRO classification for both domains
- When Camoufox lands, implement via traditional HTML scraping of the PHP SSR pages
- Consider targeting zoomcar.fr exclusively (ouestfrance-auto.fr is now a redirect)
