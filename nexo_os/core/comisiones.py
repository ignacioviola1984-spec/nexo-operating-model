"""Seguimiento de comisiones deterministic figures.

Expected vs settled, discrepancies (diferencia_ars derived), aging of the
commission receivable anchored to the period (not the nullable fecha_liquidacion),
and totals by insurer/period. Settlement-grade rigor: this protects the broker's
own revenue.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import dias_aging_comision
from nexo_os.core.money import ZERO, total
from nexo_os.data.schema.models import Comision


@dataclass(frozen=True)
class ComisionItem:
    comision_id: str
    poliza_id: str
    aseguradora_id: str
    periodo: str
    esperada_ars: Decimal
    liquidada_ars: Decimal
    diferencia_ars: Decimal
    dias_aging: int
    estado: str


@dataclass(frozen=True)
class ComisionResult:
    total_esperada_ars: Decimal
    total_liquidada_ars: Decimal
    total_diferencia_ars: Decimal
    discrepancia_count: int
    discrepancias: list[ComisionItem]
    aged_count: int
    aged_ars: Decimal
    aged_receivables: list[ComisionItem]
    diferencia_por_aseguradora: dict[str, Decimal]
    # For reconciliation with cartera (current period).
    periodo_actual: str
    base_periodo_actual_ars: Decimal
    esperada_periodo_actual_ars: Decimal


def _item(c: Comision, as_of: date, terms_offset: int) -> ComisionItem:
    liquidada = c.comision_liquidada_ars or ZERO
    diferencia = c.comision_esperada_ars - liquidada
    aging = dias_aging_comision(c.periodo, as_of, terms_offset) if diferencia > ZERO else 0
    return ComisionItem(
        comision_id=c.comision_id,
        poliza_id=c.poliza_id,
        aseguradora_id=c.aseguradora_id,
        periodo=c.periodo,
        esperada_ars=c.comision_esperada_ars,
        liquidada_ars=liquidada,
        diferencia_ars=diferencia,
        dias_aging=aging,
        estado=str(c.estado),
    )


def compute_comisiones(
    comisiones: list[Comision],
    *,
    as_of: date,
    thresholds: Thresholds,
    periodo_actual: str | None = None,
) -> ComisionResult:
    periodo_actual = periodo_actual or f"{as_of:%Y-%m}"
    offset = thresholds.commission_terms_offset_days
    items = [_item(c, as_of, offset) for c in comisiones]

    total_esperada = total([it.esperada_ars for it in items])
    total_liquidada = total([it.liquidada_ars for it in items])
    total_diferencia = total([it.diferencia_ars for it in items])

    discrepancias = [it for it in items if it.diferencia_ars > ZERO]
    discrepancias.sort(
        key=lambda it: (float(it.diferencia_ars) * max(it.dias_aging, 1)), reverse=True
    )

    aged = [it for it in items if it.dias_aging > 0]
    aged.sort(key=lambda it: it.dias_aging, reverse=True)

    por_aseg: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for it in items:
        por_aseg[it.aseguradora_id] += it.diferencia_ars

    base_actual = total(
        [c.base_comisionable_ars for c in comisiones if c.periodo == periodo_actual]
    )
    esperada_actual = total(
        [c.comision_esperada_ars for c in comisiones if c.periodo == periodo_actual]
    )

    return ComisionResult(
        total_esperada_ars=total_esperada,
        total_liquidada_ars=total_liquidada,
        total_diferencia_ars=total_diferencia,
        discrepancia_count=len(discrepancias),
        discrepancias=discrepancias,
        aged_count=len(aged),
        aged_ars=total([it.diferencia_ars for it in aged]),
        aged_receivables=aged,
        diferencia_por_aseguradora={k: total([v]) for k, v in por_aseg.items()},
        periodo_actual=periodo_actual,
        base_periodo_actual_ars=base_actual,
        esperada_periodo_actual_ars=esperada_actual,
    )
