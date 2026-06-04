# autoweek.nl — TIER-1 (Akamai + DPG Media WAF, no Tier-0 implementation)

> Research date: 2026-06-03. Method: live `curl` probes with Chrome 130/136 UA from a datacenter egress (no proxy, no impersonation). Every probed path was blocked at the edge by Akamai Bot Manager + DPG Media's custom WAF, including paths that are normally allowed unauthenticated (`robots.txt`, `/sitemap.xml`). The portal cannot be reached with `curl_cffi` chrome impersonation alone and is therefore deferred to the stealth-browser tier.

---

## Verdict: TIER-1 (skip Tier-0 implementation, document for the engine)

`autoweek.nl` is a DPG Media (NL/BE conglomerate; same group as Tweakers, NU.nl, AD) property fronted by **AkamaiGHost + DPG Media WAF**. Plain `curl` returns `403 Forbidden` with the explicit fingerprint `x-blocked-by-waf: true` and the DPG Access Denied body **on every URL**, including `/robots.txt` — that is a hard WAF, not a per-path rule.

For the CARDEX engine this is the same class as mobile.de / kleinanzeigen.de: Akamai_v3 challenge on the SRP, no T1 path. We add a `domain_map.py` registry entry so the coordinator can dispatch a stealth browser (T2) and optionally escalate to T3, but **do not ship a Tier-0/Tier-1 scraper module** that would only generate 403s in production.

---

## Anti-bot stack [VERIFIED 2026-06-03]

```
$ curl -skI -A "Mozilla/5.0 … Chrome/136.0.0.0 Safari/537.36" https://www.autoweek.nl/
HTTP/1.1 403 Forbidden
Server: AkamaiGHost
x-blocked-by-waf: true
x-ak-reference-id: 0.cf2bf7c1.1780524696.8b2c74a
x-ak-client-ip: 2a02:1210:1c16:4100:b33c:92d5:ec54:5dad
…
```

The body returned is DPG Media's "Access Denied" template:

```html
<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY>
<H1>Access Denied</H1>
<P>Your request was blocked by DPG Media's Web Application Firewall.</P>
…
```

Same response on `/robots.txt`, `/sitemap.xml`, `/occasions/`, `/aanbod`. Naked `curl_cffi` `impersonate="chrome"` is the standard T1 baseline — and this portal blocks on the TLS/HTTP2/header layer that JA3 alone does not satisfy. There is no Tier-1 surface to onboard.

| Surface | Method | Result |
|---|---|---|
| `/` | `GET` Chrome 130 UA | 403 AkamaiGHost (`x-blocked-by-waf: true`) |
| `/` | `GET` Chrome 136 UA | 403 AkamaiGHost |
| `/robots.txt` | `GET` | 403 AkamaiGHost — DPG WAF body |
| `/sitemap.xml` | `HEAD` | 403 AkamaiGHost |
| `/occasions/` | `HEAD` | 403 AkamaiGHost |
| `/aanbod` | `HEAD` | 403 AkamaiGHost |

---

## Engine classification

```python
PortalSpec(
    "autoweek.nl",
    Tier.T2, WAF.AKAMAI_V3,
    can_escalate_to=Tier.T3,
    countries=["NL"],
    notes="DPG Media — Akamai Bot Manager + DPG WAF on every surface incl. robots.txt [VERIFIED 2026-06-03]",
)
```

Rationale for `can_escalate_to=Tier.T3`: DPG also runs DataDome on some surfaces of sister sites (NU.nl, Tweakers); if Akamai_v3 alone proves insufficient at scale, escalating to behavioural + residential is the documented next step. Until a stealth-browser implementation lands, the coordinator should not dispatch the portal at all (no Tier-0 module is registered).

---

## Action

- ✅ Add `autoweek.nl` to `scrapers/engine/router/domain_map.py` as T2/Akamai (escalates T3).
- ❌ **No** `scrapers/portals/autoweek_nl/` module.
- ❌ **No** entry in `scrapers/portals/__init__.py`.
- When the engine grows a Camoufox+_abck path for DPG hosts (mobile.de pattern), revisit and add a real implementation.
