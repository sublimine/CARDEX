// Package ua provides the canonical CardexBot user-agent string used by
// all HTTP clients in the discovery module.
//
// All discovery families and the browser package must use CardexUA — never
// spoof browser user-agents. CI enforces this constraint via an illegal-pattern
// scan that rejects any user-agent string not matching the CardexBot pattern.
package ua

// CardexUA is the canonical user-agent string for all CARDEX crawlers.
// Format follows RFC 7231 §5.5.3 product token convention.
const CardexUA = "CardexBot/1.0 (+https://cardex.eu/bot; indexing@cardex.eu)"
