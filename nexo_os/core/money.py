"""Money + ratio primitives for the deterministic core.

All currency math is `Decimal` (never float); rounding rules are defined once
here and applied consistently. Money is ARS unless a field says otherwise.
Ratios (rates, shares, HHI) are derived in code and returned as float for display
and deterministic scoring - the model never produces any of these.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")


def ars(value: Decimal | int | str) -> Decimal:
    """Quantize to 2 decimal places, ARS, round-half-up. The one rounding rule."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def total(values: Iterable[Decimal]) -> Decimal:
    """Exact Decimal sum (no float), then quantized to cents."""
    acc = ZERO
    for v in values:
        acc += v
    return ars(acc)


def ratio(numerator: Decimal, denominator: Decimal) -> float | None:
    """Safe ratio in [0, inf). Returns None when the denominator is zero
    (caller surfaces 'sin datos', never a fabricated 0)."""
    if denominator == ZERO:
        return None
    return float(numerator / denominator)


def share(part: Decimal, whole: Decimal) -> float:
    """Fractional share in [0, 1]; 0.0 when whole is zero."""
    if whole == ZERO:
        return 0.0
    return float(part / whole)


def hhi(parts: Iterable[Decimal], whole: Decimal) -> float | None:
    """Herfindahl-Hirschman Index = sum(share_i^2). None when whole is zero."""
    if whole == ZERO:
        return None
    acc = 0.0
    for p in parts:
        s = float(p / whole)
        acc += s * s
    return acc


def pct_change(current: Decimal, previous: Decimal) -> float | None:
    """(current - previous) / previous. None when previous is zero/absent."""
    if previous == ZERO:
        return None
    return float((current - previous) / previous)
