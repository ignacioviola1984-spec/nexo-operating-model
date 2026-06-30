"""Cobranza y morosidad (collections + delinquency) deterministic figures.

Outstanding by aging bucket, count and ARS overdue, delinquency rate, a
weighted-average days-overdue (DSO proxy), recovery priority (amount x age x
client value), and trend vs the prior snapshot. Measurement (morosidad) and
action inputs (cobranza) in one place; both stay visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import bucket_mora, dias_mora, is_overdue, outstanding
from nexo_os.core.money import ZERO, ratio, total
from nexo_os.data.schema.models import BucketMora, Cliente, Cuota

_BUCKET_ORDER = [
    BucketMora.b1_30.value,
    BucketMora.b31_60.value,
    BucketMora.b61_90.value,
    BucketMora.b90_plus.value,
]


@dataclass(frozen=True)
class OverdueItem:
    cuota_id: str
    poliza_id: str
    cliente_id: str | None
    dias_mora: int
    bucket: str
    outstanding_ars: Decimal
    segmento: str
    recovery_score: float


@dataclass(frozen=True)
class CobranzaResult:
    overdue_count: int
    total_overdue_ars: Decimal
    total_receivable_ars: Decimal
    delinquency_rate: float | None
    dias_mora_promedio_ponderado: float | None
    bucket_counts: dict[str, int]
    bucket_ars: dict[str, Decimal]
    items: list[OverdueItem]
    sin_base_comparacion: bool
    delta_overdue_ars: Decimal | None = field(default=None)


def _cliente_poliza_index(
    cuotas: list[Cuota], polizas, clientes
) -> tuple[dict[str, str], dict[str, str]]:
    cliente_by_poliza = {p.poliza_id: p.cliente_id for p in polizas}
    seg_by_cliente = {c.cliente_id: (c.segmento or "sin_segmento") for c in clientes}
    return cliente_by_poliza, seg_by_cliente


def compute_cobranza(
    cuotas: list[Cuota],
    polizas,
    clientes: list[Cliente],
    *,
    as_of: date,
    thresholds: Thresholds,
    prev_cuotas: list[Cuota] | None = None,
    prev_as_of: date | None = None,
) -> CobranzaResult:
    cliente_by_poliza, seg_by_cliente = _cliente_poliza_index(cuotas, polizas, clientes)
    bounds = thresholds.mora_bucket_bounds

    items: list[OverdueItem] = []
    bucket_counts: dict[str, int] = dict.fromkeys(_BUCKET_ORDER, 0)
    bucket_ars: dict[str, Decimal] = {b: ZERO for b in _BUCKET_ORDER}

    for c in cuotas:
        if not is_overdue(c, as_of):
            continue
        dias = dias_mora(c, as_of)
        b = bucket_mora(dias, bounds).value
        owed = outstanding(c)
        cliente_id = cliente_by_poliza.get(c.poliza_id)
        seg = seg_by_cliente.get(cliente_id, "sin_segmento")
        weight = thresholds.recovery_premium_weight if seg == "premium" else 1.0
        score = float(owed) * dias * weight
        items.append(
            OverdueItem(
                cuota_id=c.cuota_id,
                poliza_id=c.poliza_id,
                cliente_id=cliente_id,
                dias_mora=dias,
                bucket=b,
                outstanding_ars=owed,
                segmento=seg,
                recovery_score=score,
            )
        )
        bucket_counts[b] += 1
        bucket_ars[b] = bucket_ars[b] + owed

    items.sort(key=lambda it: (it.recovery_score, it.outstanding_ars), reverse=True)

    total_overdue = total([it.outstanding_ars for it in items])
    # Total receivable = outstanding over ALL unpaid installments (any due date).
    total_receivable = total([outstanding(c) for c in cuotas])
    delinquency_rate = ratio(total_overdue, total_receivable)

    weighted_days = None
    if total_overdue > ZERO:
        num = sum(Decimal(it.dias_mora) * it.outstanding_ars for it in items)
        weighted_days = float(num / total_overdue)

    sin_base = prev_cuotas is None
    delta_overdue: Decimal | None = None
    if not sin_base:
        prev_anchor = prev_as_of or as_of
        prev_overdue = total(
            [outstanding(c) for c in (prev_cuotas or []) if is_overdue(c, prev_anchor)]
        )
        delta_overdue = total_overdue - prev_overdue

    return CobranzaResult(
        overdue_count=len(items),
        total_overdue_ars=total_overdue,
        total_receivable_ars=total_receivable,
        delinquency_rate=delinquency_rate,
        dias_mora_promedio_ponderado=weighted_days,
        bucket_counts=bucket_counts,
        bucket_ars=bucket_ars,
        items=items,
        sin_base_comparacion=sin_base,
        delta_overdue_ars=delta_overdue,
    )
