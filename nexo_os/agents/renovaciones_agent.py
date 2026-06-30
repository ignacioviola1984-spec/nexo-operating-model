"""Renovaciones agent (renewals + retention).

The broker's retention lever: renewal-outreach actions for policies expiring
within the horizon, ranked by commission at stake; at-risk renewals get the
highest priority. Risk is computed without siniestros when absent (labeled).
"""

from __future__ import annotations

import json

from nexo_os.agents import scoring
from nexo_os.agents.base import Agent, build_accion, grounded_draft
from nexo_os.config import Settings, Thresholds, get_settings
from nexo_os.core.renovaciones import RenovacionResult, compute_renovaciones
from nexo_os.pii import first_name
from nexo_os.state import NexoContext


class RenovacionesAgent(Agent):
    nombre = "renovaciones"

    def __init__(self, thresholds: Thresholds, settings: Settings | None = None):
        self.thresholds = thresholds
        self.settings = settings or get_settings()

    def compute(self, ctx: NexoContext) -> RenovacionResult:
        repo = ctx.repo
        return compute_renovaciones(
            repo.get_polizas(),
            repo.get_cuotas(),
            repo.get_siniestros(),
            as_of=ctx.snapshot_fecha,
            thresholds=self.thresholds,
            has_siniestros=repo.has_siniestros(),
        )

    def propose(self, ctx: NexoContext, result: RenovacionResult):
        name_by_id = {c.cliente_id: first_name(c.nombre) for c in ctx.repo.get_clientes()}
        acciones = []
        for it in result.items:
            cliente = name_by_id.get(it.cliente_id, "el cliente")
            comision = int(it.comision_estimada_ars)
            signal = 0.95 if it.at_risk else 0.65
            data_ok = scoring.completeness([bool(it.cliente_id), it.prima_ars > 0])
            conf = scoring.confidence(data_ok, signal, self.thresholds)
            prioridad = scoring.priority(
                it.comision_estimada_ars,
                scoring.urgency_from_deadline(it.dias_a_vencer, self.thresholds),
                self.thresholds,
            )
            rationale = {
                "cliente": cliente,
                "dias_a_vencer": it.dias_a_vencer,
                "comision_en_juego_ars": comision,
                "en_riesgo": it.at_risk,
                "ramo": it.ramo,
                "usa_siniestros": result.usa_siniestros,
            }
            acciones.append(
                build_accion(
                    ctx,
                    agente=self.nombre,
                    tipo_accion="renovacion_riesgo" if it.at_risk else "renovacion",
                    entidad_tipo="poliza",
                    entidad_id=it.poliza_id,
                    prioridad=prioridad,
                    confianza=conf,
                    monto_en_juego_ars=it.comision_estimada_ars,
                    rationale=rationale,
                )
            )
        return acciones

    def narrate(self, ctx: NexoContext, result: RenovacionResult, accion):
        r = json.loads(accion.rationale_json)
        riesgo = " Es una renovacion en riesgo: priorizar." if r["en_riesgo"] else ""
        fallback = (
            f"Contactar a {r['cliente']} por la renovacion de su poliza de {r['ramo']}: "
            f"vence en {r['dias_a_vencer']} dias, con ARS {r['comision_en_juego_ars']} "
            f"de comision en juego.{riesgo}"
        )
        return grounded_draft(
            accion,
            instruccion="Redacta un contacto de renovacion orientado a retener al cliente.",
            fallback=fallback,
            settings=self.settings,
        )
