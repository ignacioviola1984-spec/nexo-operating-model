"""Reliability layer: deterministic cross-agent reconciliations (§10/§11).

These cross-checks tie the agents' figures together. On a break beyond tolerance
the run is marked con_warnings and the break is surfaced - never silently
smoothed. Tolerances live in config.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.cartera import CarteraResult
from nexo_os.core.cobranza import CobranzaResult
from nexo_os.core.comisiones import ComisionResult
from nexo_os.core.renovaciones import RenovacionResult


@dataclass(frozen=True)
class ReconCheck:
    nombre: str
    ok: bool
    severidad: str  # baja when ok, alta on break
    detalle: str


def _ties(a: Decimal, b: Decimal, thresholds: Thresholds) -> bool:
    diff = abs(a - b)
    if diff <= thresholds.reconciliation_abs_tolerance_ars:
        return True
    if b != 0:
        return abs(diff / b) <= Decimal(str(thresholds.reconciliation_rel_tolerance))
    return diff == 0


def reconcile(
    cartera: CarteraResult,
    comisiones: ComisionResult,
    cobranza: CobranzaResult,
    renovaciones: RenovacionResult,
    *,
    thresholds: Thresholds,
) -> list[ReconCheck]:
    checks: list[ReconCheck] = []

    # 1) cartera in-force premium ties to comisiones current-period base.
    ok = _ties(cartera.prima_total, comisiones.base_periodo_actual_ars, thresholds)
    checks.append(
        ReconCheck(
            "cartera_premium_vs_comisiones_base",
            ok,
            "baja" if ok else "alta",
            f"prima_total={cartera.prima_total} vs base_periodo={comisiones.base_periodo_actual_ars}",
        )
    )

    # 2) cartera expected commission ties to comisiones current-period esperada.
    ok = _ties(cartera.comision_esperada_total, comisiones.esperada_periodo_actual_ars, thresholds)
    checks.append(
        ReconCheck(
            "cartera_comision_vs_comisiones_esperada",
            ok,
            "baja" if ok else "alta",
            f"comision_esperada={cartera.comision_esperada_total} vs "
            f"esperada_periodo={comisiones.esperada_periodo_actual_ars}",
        )
    )

    # 3) cobranza overdue total is internally consistent with its bucket breakdown.
    bucket_sum = sum(cobranza.bucket_ars.values(), Decimal("0"))
    ok = _ties(bucket_sum, cobranza.total_overdue_ars, thresholds)
    checks.append(
        ReconCheck(
            "cobranza_buckets_suman_total",
            ok,
            "baja" if ok else "alta",
            f"suma_buckets={bucket_sum} vs total_overdue={cobranza.total_overdue_ars}",
        )
    )

    # 4) renovaciones at-risk premium is a subset of cartera in-force premium.
    ok = (
        renovaciones.at_risk_prima_ars
        <= cartera.prima_total + thresholds.reconciliation_abs_tolerance_ars
    )
    checks.append(
        ReconCheck(
            "renovaciones_at_risk_subset_cartera",
            ok,
            "baja" if ok else "alta",
            f"at_risk_prima={renovaciones.at_risk_prima_ars} <= prima_total={cartera.prima_total}",
        )
    )

    return checks
