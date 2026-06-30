"""Deterministic confidence + priority (§11). Never model-produced.

Confidence is a documented function of data completeness and signal strength.
Priority is derived from the ARS amount at stake and urgency; when there is no
natural amount (monto_en_juego_ars is null) it falls back to an URGENCY-ONLY
branch and never substitutes or infers an amount.
"""

from __future__ import annotations

from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.data.schema.models import Prioridad

_SEVERITY = {Prioridad.alta: 3, Prioridad.media: 2, Prioridad.baja: 1}


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def confidence(data_completeness: float, signal_strength: float, thresholds: Thresholds) -> float:
    """W_DATA·completeness + W_SIGNAL·signal, both clamped to [0,1]."""
    c = clamp01(data_completeness)
    s = clamp01(signal_strength)
    return round(thresholds.conf_weight_data * c + thresholds.conf_weight_signal * s, 4)


def completeness(flags: list[bool]) -> float:
    """Fraction of present/usable data fields. Empty -> 0.0."""
    if not flags:
        return 0.0
    return sum(1 for f in flags if f) / len(flags)


def amount_tier(monto: Decimal | None, thresholds: Thresholds) -> Prioridad | None:
    """Priority tier implied by the amount at stake, or None when there is none."""
    if monto is None:
        return None
    if monto >= thresholds.priority_alta_ars:
        return Prioridad.alta
    if monto >= thresholds.priority_media_ars:
        return Prioridad.media
    return Prioridad.baja


def urgency_from_deadline(days_to_deadline: int, thresholds: Thresholds) -> Prioridad:
    """Deadline-style urgency: fewer days = more urgent (e.g. days to expiry)."""
    if days_to_deadline <= thresholds.priority_urgent_days:
        return Prioridad.alta
    if days_to_deadline <= thresholds.priority_urgent_days * 4:
        return Prioridad.media
    return Prioridad.baja


def urgency_from_age(days_aged: int, thresholds: Thresholds) -> Prioridad:
    """Age-style urgency: more days = more urgent (e.g. days overdue/aged)."""
    if days_aged >= thresholds.priority_urgent_days * 12:  # ~90d
        return Prioridad.alta
    if days_aged >= thresholds.priority_urgent_days * 4:  # ~28d
        return Prioridad.media
    return Prioridad.baja


def priority(
    monto: Decimal | None,
    urgency: Prioridad | None,
    thresholds: Thresholds,
) -> Prioridad:
    """Combine amount tier and urgency tier (take the more severe). With no
    amount AND no urgency, defaults to baja - never invents an amount."""
    tiers = [t for t in (amount_tier(monto, thresholds), urgency) if t is not None]
    if not tiers:
        return Prioridad.baja
    return max(tiers, key=lambda t: _SEVERITY[t])
