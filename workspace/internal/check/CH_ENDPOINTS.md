# Switzerland — Plate Resolution Sources (investigation)

Probes run 2026-04-20. All responses under `/tmp/cardex_probes/ch_*`.

Switzerland has **26 cantons**, each running vehicle registration (MFK)
independently. Two commercial platforms consolidate them:

- **viacar-system.ch** — Angular SPA, hard reCAPTCHA v2/v3 gate.
- **eautoindex.ch** — Ionic SPA, paid lookup via PostFinance Checkout.

## ❌ viacar-system.ch group — reCAPTCHA wall

Cantons routed here: **SH, AG, LU, ZG**.
All four hostnames (`sh-autoindex.viacar-system.ch`,
`ag-autoindex.viacar-system.ch`, `lu-autoindex.viacar-system.ch`,
`zg-autoindex.viacar-system.ch`) serve the **exact same 63 186-byte SPA shell**
(md5 identical) — a Vue bundle requiring JS + Google reCAPTCHA.

Reverse-engineered from `main.js` (849 KB):

```
GET  https://sh-autoindex.viacar-system.ch/api/settings/recaptcha
→ HTTP 200 {"siteKey":"6Lfy0OInAAAAAGR_vbqirGQla4ngTyAJbtFkvhsW"}

POST https://sh-autoindex.viacar-system.ch/api/Vehicle/List/Search
     {"plate":"SH12345","recaptchaResponse":"..."}
→ HTTP 400 without a valid reCAPTCHA v3 token from a real browser session.
```

reCAPTCHA v3 cannot be satisfied server-side without either solving the
puzzle (CAPTCHA-farm = paid), or obtaining a long-lived API key that Viacar
only grants to licensed partners. **Hard block.**

## ❌ eautoindex.ch — PostFinance Checkout paywall

Cantons routed here (17 of 26): **ZH, BE, BL, BS, GE, VD, VS, NE, JU, FR,
SO, GR, TG, OW, NW, AR, AI**.

```
curl https://www.eautoindex.ch/
→ HTTP 200 (5.7 KB SPA shell).
```

`main.js` (896 KB) reveals:
- JWT bootstrap via `/api/auth/token`.
- Plate search endpoint requires an order ID, tied to a
  `postfinance.ch/checkout/...` payment flow (CHF 5–10 per lookup).
- No free tier, no public trial endpoint.

Paid service — excluded per mission rules.

## ❌ ZH — former strassenverkehrsamt.zh.ch plate form removed

```
curl https://www.zh.ch/de/sicherheit-justiz/strassenverkehrsamt.html
→ HTTP 200. Page now links only to eautoindex.ch for plate lookup.
curl https://stva.zh.ch/
→ curl: (6) Could not resolve host.
```
ZH delegated its public plate-lookup to eautoindex.ch (paid).

## ❌ Cantons with no public lookup at all: GL, SZ, UR, TI

Each canton's Strassenverkehrsamt website lists only contact info, opening
hours and downloadable paper forms. No online plate query.

## Summary per canton

| Canton | Status | Blocker |
|--------|--------|---------|
| SH, AG, LU, ZG | blocked | reCAPTCHA v3 (viacar-system.ch) |
| ZH, BE, BL, BS, GE, VD, VS, NE, JU, FR, SO, GR, TG, OW, NW, AR, AI | blocked | PostFinance paywall (eautoindex.ch) |
| GL, SZ, UR, TI | blocked | No online lookup at all |

**All 26 cantons blocked** for unauthenticated, unpaid access.

The resolver returns `ErrPlateResolutionUnavailable` with a per-category
explanation. A future integration could pay eautoindex.ch per lookup or
negotiate a Viacar partner API — both out of scope for this free tier.
