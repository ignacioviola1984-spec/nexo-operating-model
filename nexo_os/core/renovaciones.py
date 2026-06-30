"""Renovaciones (renewals + retention) deterministic figures.

Policies expiring in 30/60/90 days, renewal rate, premium and commission at
stake, and at-risk renewals (nearing expiry + overdue installments + claim
history + no successor policy). If siniestros is absent the risk is computed
without it and labeled as such (graceful degradation), never failing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.aging import is_overdue
from nexo_os.core.money import ars, ratio, total
from nexo_os.data.schema.models import Cuota, EstadoPoliza, Poliza, Siniestro


@dataclass(frozen=True)
class RenovacionItem:
    poliza_id: str
    cliente_id: str
    aseguradora_id: str
    ramo: str
    dias_a_vencer: int
    prima_ars: Decimal
    comision_estimada_ars: Decimal
    tiene_mora: bool
    tiene_siniestro: bool
    tiene_sucesor: bool
    at_risk: bool
    risk_score: float


@dataclass(frozen=True)
class RenovacionResult:
    expiring_30: int
    expiring_60: int
    expiring_90: int
    prima_en_juego_90_ars: Decimal
    comision_en_juego_90_ars: Decimal
    at_risk_count: int
    at_risk_prima_ars: Decimal
    at_risk_items: list[RenovacionItem]
    items: list[RenovacionItem]
    renovadas_count: int
    vencidas_no_renovadas_count: int
    renewal_rate: float | None
    usa_siniestros: bool = field(default=True)


def compute_renovaciones(
    polizas: list[Poliza],
    cuotas: list[Cuota],
    siniestros: list[Siniestro],
    *,
    as_of: date,
    thresholds: Thresholds,
    has_siniestros: bool = True,
) -> RenovacionResult:
    w30, w60, w90 = thresholds.renewal_windows_days
    overdue_polizas = {c.poliza_id for c in cuotas if is_overdue(c, as_of)}
    claim_polizas = {s.poliza_id for s in siniestros} if has_siniestros else set()
    successors = {p.poliza_origen_id for p in polizas if p.poliza_origen_id}

    items: list[RenovacionItem] = []
    for p in polizas:
        if p.estado != EstadoPoliza.vigente:
            continue
        dias = (p.fecha_fin_vigencia - as_of).days
        if dias < 0 or dias > w90:
            continue
        tiene_mora = p.poliza_id in overdue_polizas
        tiene_sin = p.poliza_id in claim_polizas
        tiene_suc = p.poliza_id in successors
        near = dias <= w30
        score = (
            0.4 * float(near)
            + 0.3 * float(tiene_mora)
            + (0.2 * float(tiene_sin) if has_siniestros else 0.0)
            + 0.1 * float(not tiene_suc)
        )
        at_risk = near and (not tiene_suc) and (tiene_mora or tiene_sin)
        comision = ars(p.prima_ars * p.comision_pct)
        items.append(
            RenovacionItem(
                poliza_id=p.poliza_id,
                cliente_id=p.cliente_id,
                aseguradora_id=p.aseguradora_id,
                ramo=str(p.ramo),
                dias_a_vencer=dias,
                prima_ars=p.prima_ars,
                comision_estimada_ars=comision,
                tiene_mora=tiene_mora,
                tiene_siniestro=tiene_sin,
                tiene_sucesor=tiene_suc,
                at_risk=at_risk,
                risk_score=round(score, 4),
            )
        )

    items.sort(key=lambda it: (it.comision_estimada_ars, it.dias_a_vencer), reverse=True)
    expiring_30 = sum(1 for it in items if it.dias_a_vencer <= w30)
    expiring_60 = sum(1 for it in items if it.dias_a_vencer <= w60)
    expiring_90 = len(items)

    at_risk_items = [it for it in items if it.at_risk]
    at_risk_items.sort(key=lambda it: it.comision_estimada_ars, reverse=True)

    renovadas = sum(1 for p in polizas if p.estado == EstadoPoliza.renovada)
    vencidas = sum(1 for p in polizas if p.estado == EstadoPoliza.vencida)
    renewal_rate = ratio(Decimal(renovadas), Decimal(renovadas + vencidas))

    return RenovacionResult(
        expiring_30=expiring_30,
        expiring_60=expiring_60,
        expiring_90=expiring_90,
        prima_en_juego_90_ars=total([it.prima_ars for it in items]),
        comision_en_juego_90_ars=total([it.comision_estimada_ars for it in items]),
        at_risk_count=len(at_risk_items),
        at_risk_prima_ars=total([it.prima_ars for it in at_risk_items]),
        at_risk_items=at_risk_items,
        items=items,
        renovadas_count=renovadas,
        vencidas_no_renovadas_count=vencidas,
        renewal_rate=renewal_rate,
        usa_siniestros=has_siniestros,
    )
