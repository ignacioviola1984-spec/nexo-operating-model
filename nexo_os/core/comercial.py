"""Pipeline comercial (pipeline + conversion + lead/quote control) figures.

Open pipeline value, stage distribution, weighted forecast (stage probabilities
from config), lead-to-win and quote-to-bind conversion, velocity/aging in stage,
quotes issued but never presented, and leads with no quote past a window. A quote
is 'bound' when cotizaciones.poliza_id is set (never inferred).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core.money import ZERO, ars, ratio, total
from nexo_os.data.schema.models import Cotizacion, EstadoLead, Lead

_CLOSED = {EstadoLead.ganado, EstadoLead.perdido}


@dataclass(frozen=True)
class OpportunityItem:
    lead_id: str
    estado: str
    ramo: str
    productor_id: str
    canal_origen: str
    valor_ars: Decimal
    probabilidad: float
    valor_ponderado_ars: Decimal
    dias_en_etapa: int


@dataclass(frozen=True)
class FunnelFlag:
    tipo: str  # sin_cotizacion | no_presentada | estancado
    entidad_id: str  # lead_id or cotizacion_id
    lead_id: str
    dias: int
    detalle: str


@dataclass(frozen=True)
class ComercialResult:
    leads_total: int
    open_count: int
    stage_distribution: dict[str, int]
    quotes_total: int
    quotes_bound: int
    quote_to_bind: float | None
    won: int
    lost: int
    closed: int
    lead_to_win_closed: float | None
    lead_to_win_total: float | None
    pipeline_value_ars: Decimal
    weighted_forecast_ars: Decimal
    opportunities: list[OpportunityItem]
    funnel_flags: list[FunnelFlag]
    sin_cotizacion_count: int
    no_presentada_count: int
    estancado_count: int


def _last_move(lead: Lead) -> date:
    return lead.fecha_ultimo_movimiento or lead.fecha_ingreso


def compute_comercial(
    leads: list[Lead],
    cotizaciones: list[Cotizacion],
    *,
    as_of: date,
    thresholds: Thresholds,
) -> ComercialResult:
    probs = thresholds.stage_probabilities
    quotes_by_lead: dict[str, list[Cotizacion]] = defaultdict(list)
    for q in cotizaciones:
        quotes_by_lead[q.lead_id].append(q)

    stage_dist: dict[str, int] = defaultdict(int)
    for ld in leads:
        stage_dist[str(ld.estado)] += 1

    open_leads = [ld for ld in leads if ld.estado not in _CLOSED]

    # Opportunities (open leads), valued by their best quote.
    opportunities: list[OpportunityItem] = []
    for ld in open_leads:
        quotes = quotes_by_lead.get(ld.lead_id, [])
        valor = max((q.prima_cotizada_ars for q in quotes), default=ZERO)
        prob = probs.get(str(ld.estado), 0.0)
        ponderado = ars(valor * Decimal(str(prob)))
        opportunities.append(
            OpportunityItem(
                lead_id=ld.lead_id,
                estado=str(ld.estado),
                ramo=str(ld.ramo),
                productor_id=ld.productor_id,
                canal_origen=str(ld.canal_origen),
                valor_ars=valor,
                probabilidad=prob,
                valor_ponderado_ars=ponderado,
                dias_en_etapa=(as_of - _last_move(ld)).days,
            )
        )
    opportunities.sort(key=lambda o: o.valor_ars, reverse=True)

    pipeline_value = total([o.valor_ars for o in opportunities])
    weighted_forecast = total([o.valor_ponderado_ars for o in opportunities])

    # Conversion.
    won = sum(1 for ld in leads if ld.estado == EstadoLead.ganado)
    lost = sum(1 for ld in leads if ld.estado == EstadoLead.perdido)
    closed = won + lost
    quotes_total = len(cotizaciones)
    quotes_bound = sum(1 for q in cotizaciones if q.poliza_id is not None)

    # Funnel flags (disjoint by construction).
    flags: list[FunnelFlag] = []
    sin_cotizacion_leads: set[str] = set()
    for ld in open_leads:
        if not quotes_by_lead.get(ld.lead_id):
            dias = (as_of - ld.fecha_ingreso).days
            if dias > thresholds.lead_no_quote_days:
                sin_cotizacion_leads.add(ld.lead_id)
                flags.append(
                    FunnelFlag(
                        "sin_cotizacion",
                        ld.lead_id,
                        ld.lead_id,
                        dias,
                        f"Lead sin cotizacion hace {dias} dias.",
                    )
                )

    no_presentada_leads: set[str] = set()
    for q in cotizaciones:
        if str(q.estado) == "emitida":
            dias = (as_of - q.fecha_cotizacion).days
            if dias > thresholds.quote_not_presented_days:
                no_presentada_leads.add(q.lead_id)
                flags.append(
                    FunnelFlag(
                        "no_presentada",
                        q.cotizacion_id,
                        q.lead_id,
                        dias,
                        f"Cotizacion emitida sin presentar hace {dias} dias.",
                    )
                )

    for ld in open_leads:
        if ld.lead_id in sin_cotizacion_leads or ld.lead_id in no_presentada_leads:
            continue
        dias = (as_of - _last_move(ld)).days
        if dias > thresholds.stage_aging_days:
            flags.append(
                FunnelFlag(
                    "estancado",
                    ld.lead_id,
                    ld.lead_id,
                    dias,
                    f"Lead estancado en '{ld.estado}' hace {dias} dias.",
                )
            )

    sin_cot = sum(1 for f in flags if f.tipo == "sin_cotizacion")
    no_pres = sum(1 for f in flags if f.tipo == "no_presentada")
    estancado = sum(1 for f in flags if f.tipo == "estancado")

    return ComercialResult(
        leads_total=len(leads),
        open_count=len(open_leads),
        stage_distribution=dict(stage_dist),
        quotes_total=quotes_total,
        quotes_bound=quotes_bound,
        quote_to_bind=ratio(Decimal(quotes_bound), Decimal(quotes_total)),
        won=won,
        lost=lost,
        closed=closed,
        lead_to_win_closed=ratio(Decimal(won), Decimal(closed)),
        lead_to_win_total=ratio(Decimal(won), Decimal(len(leads))),
        pipeline_value_ars=pipeline_value,
        weighted_forecast_ars=weighted_forecast,
        opportunities=opportunities,
        funnel_flags=flags,
        sin_cotizacion_count=sin_cot,
        no_presentada_count=no_pres,
        estancado_count=estancado,
    )
