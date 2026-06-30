"""Read-time derived quantities anchored to the snapshot date.

dias_mora / bucket_mora (installments) and commission-receivable aging are
computed here relative to `snapshot_fecha`, never stored - so aging can never
disagree with the snapshot.
"""

from __future__ import annotations

import calendar
from datetime import date

from nexo_os.core.money import ZERO
from nexo_os.data.schema.models import BucketMora, Cuota, EstadoCuota

# Installment states that may still owe money.
_UNPAID = {EstadoCuota.pendiente, EstadoCuota.vencida, EstadoCuota.parcial}


def outstanding(cuota: Cuota):
    """Amount still owed on an installment (monto - paid, floored at 0)."""
    if cuota.estado == EstadoCuota.pagada:
        return ZERO
    paid = cuota.monto_pagado_ars or ZERO
    rem = cuota.monto_ars - paid
    return rem if rem > ZERO else ZERO


def is_overdue(cuota: Cuota, as_of: date) -> bool:
    """Overdue = unpaid, past due relative to the snapshot, and still owes money."""
    return (
        cuota.estado in _UNPAID and cuota.fecha_vencimiento <= as_of and outstanding(cuota) > ZERO
    )


def dias_mora(cuota: Cuota, as_of: date) -> int:
    """Days overdue (>= 0). 0 when not yet due."""
    delta = (as_of - cuota.fecha_vencimiento).days
    return delta if delta > 0 else 0


def bucket_mora(dias: int, bounds: tuple[int, int, int]) -> BucketMora:
    """Map days-overdue to an aging bucket using (b1, b2, b3) upper bounds."""
    b1, b2, b3 = bounds
    if dias <= 0:
        return BucketMora.al_dia
    if dias <= b1:
        return BucketMora.b1_30
    if dias <= b2:
        return BucketMora.b31_60
    if dias <= b3:
        return BucketMora.b61_90
    return BucketMora.b90_plus


def periodo_end(periodo: str) -> date:
    """Last calendar day of a 'YYYY-MM' period."""
    year, month = (int(x) for x in periodo.split("-"))
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last)


def dias_aging_comision(periodo: str, as_of: date, terms_offset_days: int) -> int:
    """Days a commission receivable is aged: from period-end + terms offset to
    the snapshot. Anchored to the period (not the nullable fecha_liquidacion), so
    an unsettled commission still ages from a real date. 0 when not yet due."""
    from datetime import timedelta

    due = periodo_end(periodo) + timedelta(days=terms_offset_days)
    delta = (as_of - due).days
    return delta if delta > 0 else 0
