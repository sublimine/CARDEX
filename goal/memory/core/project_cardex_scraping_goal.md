---
name: CARDEX scraping — production indexing goal
description: Standing goal — scrapers must be tested against live portals and iterated until 100% inventory coverage per country is achieved
type: project
originSessionId: f40b2fe4-7b98-4b15-bea1-af705c3e870f
---
Standing goal: the 10+ portal scrapers (DE/FR/ES/NL/BE/CH) must be validated against production endpoints with the full coordinator stack (curl_cffi/Camoufox sessions, proxy tiers, country-specific egress). Current state is code-complete with verified logic (464+ tests passing), but never run against live portals.

**Why:** Code-correct scrapers are necessary but not sufficient. WAF behavior, rate limiting, geo-restrictions, and pagination edge cases only surface under real traffic. The mission is 100% vehicle inventory indexed per country — not "scraper written."

**How to apply:** After any scraping code session, the next step is always a live integration test. If a portal fails in production, investigate root cause and fix — never mark as done until live data flows. This is an iterative cycle: deploy → monitor → diagnose → fix → redeploy. No portal is "done" until it indexes real listings end-to-end.

Countries: DE (mobile.de, kleinanzeigen.de, AS24), FR (leboncoin.fr, lacentrale.fr, AS24), ES (coches.net, AS24), NL (marktplaats.nl, AS24), BE (tweedehands.be, gocar.be, AS24), CH (tutti.ch, comparis.ch, AS24).
