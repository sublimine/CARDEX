"""
FX → EUR conversion for the rich persister (A7).

The Go reference (``services/pipeline/pkg/fx``) loads ECB rates from Redis. That
package does not exist in the repo, so this is the Python stand-in. It is
deliberately conservative and *honest*: it never invents a rate.

  * EUR is always 1:1.
  * Any other currency converts only if a rate is explicitly configured
    (``FX_RATE_<CCY>`` env var, e.g. ``FX_RATE_CHF=1.05``) or passed in.
  * With no known rate, ``to_eur`` returns ``None`` — the caller then stores the
    row with a NULL ``gross_physical_cost_eur`` rather than dropping it or
    fabricating a number.

This keeps EUR markets (the bulk of the 6 target countries) exact, and makes the
single non-EUR currency (CHF) a one-line config decision rather than a guess
baked into code.
"""
from __future__ import annotations

import os
from decimal import Decimal

# 1:1 anchor. Non-EUR rates come from env (FX_RATE_<CCY>) or the explicit `rates`
# argument — never a hardcoded approximation.
_BASE_RATES: dict[str, Decimal] = {"EUR": Decimal(1)}


def load_rates_from_env() -> dict[str, Decimal]:
    """Collect ``FX_RATE_<CCY>`` env vars into a {CCY: Decimal} table (+ EUR=1)."""
    rates = dict(_BASE_RATES)
    for key, value in os.environ.items():
        if key.startswith("FX_RATE_") and value:
            ccy = key[len("FX_RATE_"):].upper()
            try:
                rates[ccy] = Decimal(str(value))
            except (ValueError, ArithmeticError):
                continue
    return rates


def to_eur(
    amount: Decimal | float | int | None,
    currency: str | None,
    rates: dict[str, Decimal] | None = None,
) -> Decimal | None:
    """
    Convert ``amount`` in ``currency`` to EUR, or ``None`` if no rate is known.

    A rate is the multiplier so that ``eur = amount * rate`` (EUR per 1 unit of
    the source currency). Returns ``None`` for a missing amount, a blank
    currency, or a currency with no configured rate — the caller decides what a
    NULL EUR means (store-with-null, here; the Go path fails-closed and drops).
    """
    if amount is None or not currency:
        return None
    table = rates if rates is not None else load_rates_from_env()
    rate = table.get(currency.strip().upper())
    if rate is None:
        return None
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    return value * rate
