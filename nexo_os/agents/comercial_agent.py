"""Pipeline comercial agent. Funnel-cleanup actions for stuck leads, unpresented
quotes, and leads with no quote past a window; figures via core."""

from __future__ import annotations

import json

from nexo_os.agents import scoring
from nexo_os.agents.base import Agent, build_accion, grounded_draft
from nexo_os.config import Settings, Thresholds, get_settings
from nexo_os.core.comercial import ComercialResult, compute_comercial
from nexo_os.pii import first_name
from nexo_os.state import NexoContext

_FLAG_SIGNAL = {"sin_cotizacion": 0.7, "no_presentada": 0.85, "estancado": 0.65}
_FLAG_INSTR = {
    "sin_cotizacion": "Redacta un recordatorio para cotizar un lead sin cotizacion.",
    "no_presentada": "Redacta un recordatorio para presentar una cotizacion emitida.",
    "estancado": "Redacta un proximo paso para destrabar un lead estancado.",
}


class ComercialAgent(Agent):
    nombre = "comercial"

    def __init__(self, thresholds: Thresholds, settings: Settings | None = None):
        self.thresholds = thresholds
        self.settings = settings or get_settings()

    def compute(self, ctx: NexoContext) -> ComercialResult:
        return compute_comercial(
            ctx.repo.get_leads(),
            ctx.repo.get_cotizaciones(),
            as_of=ctx.snapshot_fecha,
            thresholds=self.thresholds,
        )

    def propose(self, ctx: NexoContext, result: ComercialResult):
        name_by_lead = {ld.lead_id: first_name(ld.nombre_prospecto) for ld in ctx.repo.get_leads()}
        acciones = []
        for flag in result.funnel_flags:
            prospecto = name_by_lead.get(flag.lead_id, "el prospecto")
            signal = _FLAG_SIGNAL.get(flag.tipo, 0.6)
            conf = scoring.confidence(1.0, signal, self.thresholds)
            # No natural ARS amount -> urgency-only priority (never invent an amount).
            prioridad = scoring.priority(
                None, scoring.urgency_from_age(flag.dias, self.thresholds), self.thresholds
            )
            rationale = {"prospecto": prospecto, "tipo": flag.tipo, "dias": flag.dias}
            acciones.append(
                build_accion(
                    ctx,
                    agente=self.nombre,
                    tipo_accion=f"funnel_{flag.tipo}",
                    entidad_tipo="lead",
                    entidad_id=flag.entidad_id,
                    prioridad=prioridad,
                    confianza=conf,
                    monto_en_juego_ars=None,
                    rationale=rationale,
                )
            )
        return acciones

    def narrate(self, ctx: NexoContext, result: ComercialResult, accion):
        r = json.loads(accion.rationale_json)
        verbo = {
            "sin_cotizacion": "sigue sin cotizacion",
            "no_presentada": "tiene una cotizacion emitida sin presentar",
            "estancado": "esta estancado en su etapa",
        }.get(r["tipo"], "requiere seguimiento")
        fallback = (
            f"Avanzar el lead de {r['prospecto']}: {verbo} hace {r['dias']} dias. "
            "Definir el proximo paso."
        )
        return grounded_draft(
            accion,
            instruccion=_FLAG_INSTR.get(r["tipo"], "Redacta un proximo paso comercial."),
            fallback=fallback,
            settings=self.settings,
        )
