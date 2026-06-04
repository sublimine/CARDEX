# automobile.fr — REDIRECT to mobile.de

## Status: REDIRECT (not a native French portal)

## Summary
automobile.fr redirects to www.mobile.de/fr — the French-language locale of
the German mobile.de portal. Not a native French portal. mobile.de is already
implemented as a T2 scraper (Akamai V3).

## Technical Details
- Redirect: automobile.fr -> www.mobile.de/fr
- Tech: Custom framework (mobile.de stack)
- WAF: Akamai V3 (inherited from mobile.de)
- Volume: ~1.08M offers (German inventory, not French-specific)

## Decision: SKIP — redirect to already-implemented mobile.de.
