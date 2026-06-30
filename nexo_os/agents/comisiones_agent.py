"""Seguimiento de comisiones agent. Claim/dispute actions on insurers for unpaid
or underpaid commissions, prioritized by amount and age. Protects the broker's
own revenue - settlement-grade rigor."""

from __future__ import annotations

import json

from nexo_os.agents import scoring
from nexo_os.agents.base import Agent, build_accion, grounded_draft
from nexo_os.config import Settings, Thresholds, get_settings
from nexo_os.core.comisiones import ComisionResult, compute_comisiones
from nexo_os.state import NexoContext


class ComisionesAgent(Agent):
    nombre = "comisiones"

    def __init__(self, thresholds: Thresholds, settings: Settings | None = None):
        self.thresholds = thresholds
        self.settings = settings or get_settings()

    def compute(self, ctx: NexoContext) -> ComisionResult:
        return compute_comisiones(
            ctx.repo.get_comisiones(), as_of=ctx.snapshot_fecha, thresholds=self.thresholds
        )

    def propose(self, ctx: NexoContext, result: ComisionResult):
        name_by_aseg = {a.aseguradora_id: a.nombre for a in ctx.repo.get_aseguradoras()}
        acciones = []
        for it in result.discrepancias:
            nombre = name_by_aseg.get(it.aseguradora_id, "la aseguradora")
            diferencia = int(it.diferencia_ars)
            # Signal stronger when aged; confidence high (settlement data is exact).
            signal = 0.95 if it.dias_aging > 0 else 0.8
            conf = scoring.confidence(1.0, signal, self.thresholds)
            prioridad = scoring.priority(
                it.diferencia_ars,
                scoring.urgency_from_age(it.dias_aging, self.thresholds),
                self.thresholds,
            )
            rationale = {
                "aseguradora": nombre,
                "diferencia_ars": diferencia,
                "dias_aging": it.dias_aging,
            }
            acciones.append(
                build_accion(
                    ctx,
                    agente=self.nombre,
                    tipo_accion="reclamo_comision",
                    entidad_tipo="comision",
                    entidad_id=it.comision_id,
                    prioridad=prioridad,
                    confianza=conf,
                    monto_en_juego_ars=it.diferencia_ars,
                    rationale=rationale,
                )
            )
        return acciones

    def narrate(self, ctx: NexoContext, result: ComisionResult, accion):
        r = json.loads(accion.rationale_json)
        aging = (
            f" La diferencia lleva {r['dias_aging']} dias sin regularizar."
            if r["dias_aging"] > 0
            else ""
        )
        fallback = (
            f"Reclamar a {r['aseguradora']} una diferencia de comision de ARS "
            f"{r['diferencia_ars']}.{aging}"
        )
        return grounded_draft(
            accion,
            instruccion="Redacta un reclamo de comision a la aseguradora, formal y especifico.",
            fallback=fallback,
            settings=self.settings,
        )
