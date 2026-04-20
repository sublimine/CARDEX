# Belgium — Plate Resolution Sources (investigation)

Probes run 2026-04-20. All responses captured under `/tmp/cardex_probes/be_*`.

**Structural problem**: Belgian plates are **personal** (the plate follows the
owner, not the vehicle). A single plate can be transferred between vehicles, so
a nominal "plate lookup" is fundamentally ambiguous in BE. This is why public
plate databases barely exist.

## ❌ GOCA (contrôle technique Wallonie/Bruxelles)

```
curl https://www.goca.be/fr/outil-de-recherche
→ HTTP 302 redirect to https://gocavlaanderen.be/nl (Flanders-only portal)
curl https://gocavlaanderen.be/
→ HTTP 200, informational site only. NO public plate lookup form.
```
The Wallonie/Brussels CT portal (former "goca.be") has been absorbed into
the autocontrole.be group site which provides neither a form nor an API.

## ❌ Car-Pass (car-pass.be)

```
curl https://www.car-pass.be/api/report/1ABC123
→ HTTP 404 (endpoint does not exist)
curl https://www.car-pass.be/ecommerce/report/VIN
→ HTTP 404 (endpoint does not exist)
```
Car-Pass is a paid service that requires a 3-digit verification code printed
on the actual paper Car-Pass certificate handed to the buyer at purchase.
No API for uncredentialled lookup.

## ❌ DIV / mobilit.belgium.be

```
curl https://mobilit.belgium.be/fr/route/immatriculation
→ HTTP 200 but the official plate-lookup flow requires eID or itsme
  authentication (Belgian government digital ID).
```
Hard auth-wall — compliant with GDPR + Belgian privacy law.

## ❌ ecoscore.be

```
curl https://ecoscore.be/fr/rechercher-ecoscore-voiture
→ HTTP 200 (32 KB). Form takes Make + Model + Year dropdowns — no plate field.
```
Not a plate database.

## ❌ chassisnummeropzoeken.be

```
curl https://chassisnummeropzoeken.be/
→ redirects to autoverleden.nl (Dutch site)
```
Requires VIN, not plate.

## ❌ kentekencheck.be

```
curl https://kentekencheck.be/
→ HTTP 200 114 bytes — parked domain.
```

## ❌ Inspection-centre group sites (aibv.be, km.be, autoveiligheid.be)

Probed all three. Each returns an informational site describing locations and
prices; none expose a plate-lookup form or API.

## Summary

**No public BE plate→vehicle source exists.** The combination of
(1) plate-follows-owner semantics,
(2) GDPR + Belgian privacy implementation (DIV eID-only),
(3) Car-Pass's per-sale paper-code model,
means that unauthenticated plate resolution is not a solvable problem in
Belgium via current public endpoints.

The resolver must return `ErrPlateResolutionUnavailable` with this explanation.
