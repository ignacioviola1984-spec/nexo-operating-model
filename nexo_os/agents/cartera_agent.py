"""Cartera agent (portfolio). Mostly informational: review items for
over-concentration and shrinking segments. No per-client actions."""

from __future__ import annotations

import json

from nexo_os.agents import scoring
from nexo_os.agents.base import Agent, build_accion, grounded_draft
from nexo_os.config import Settings, Thresholds, get_settings
from nexo_os.core.cartera import CarteraResult, compute_cartera
from nexo_os.data.schema.models import Prioridad
from nexo_os.state import NexoContext


class CarteraAgent(Agent):
    nombre = "cartera"

    def __init__(self, thresholds: Thresholds, settings: Settings | None = None):
        self.thresholds = thresholds
        self.settings = settings or get_settings()

    def compute(self, ctx: NexoContext) -> CarteraResult:
        repo = ctx.repo
        prev_snap = repo.get_previous_snapshot()
        return compute_cartera(
            repo.get_polizas(),
            repo.get_clientes(),
            thresholds=self.thresholds,
            prev_polizas=repo.prev_polizas() if prev_snap else None,
            prev_clientes=repo.prev_clientes() if prev_snap else None,
        )

    def propose(self, ctx: NexoContext, result: CarteraResult):
        name_by_aseg = {a.aseguradora_id: a.nombre for a in ctx.repo.get_aseguradoras()}
        acciones = []
        if result.concentracion_alerta and result.aseguradora_dominante:
            nombre = name_by_aseg.get(result.aseguradora_dominante, "una aseguradora")
            share_pct = int(round(result.share_dominante * 100))
            conf = scoring.confidence(1.0, 0.85, self.thresholds)
            acciones.append(
                build_accion(
                    ctx,
                    agente=self.nombre,
                    tipo_accion="revisar_concentracion",
                    entidad_tipo="aseguradora",
                    entidad_id=result.aseguradora_dominante,
                    prioridad=scoring.priority(None, Prioridad.media, self.thresholds),
                    confianza=conf,
                    monto_en_juego_ars=None,
                    rationale={"aseguradora": nombre, "share_pct": share_pct},
                )
            )
        for seg, delta in result.segmentos_en_baja:
            caida_pct = int(round(abs(delta) * 100))
            conf = scoring.confidence(1.0, 0.8, self.thresholds)
            acciones.append(
                build_accion(
                    ctx,
                    agente=self.nombre,
                    tipo_accion="revisar_segmento",
                    entidad_tipo="segmento",
                    entidad_id=seg,
                    prioridad=scoring.priority(None, Prioridad.media, self.thresholds),
                    confianza=conf,
                    monto_en_juego_ars=None,
                    rationale={"segmento": seg, "caida_pct": caida_pct},
                )
            )
        return acciones

    def narrate(self, ctx: NexoContext, result: CarteraResult, accion):
        r = json.loads(accion.rationale_json)
        if accion.tipo_accion == "revisar_concentracion":
            fallback = (
                f"Revisar la concentracion de cartera: {r['aseguradora']} concentra el "
                f"{r['share_pct']}% de la prima en vigor. Evaluar diversificar."
            )
            instruccion = "Redacta una observacion sobre la concentracion por aseguradora."
        else:
            fallback = (
                f"Revisar el segmento {r['segmento']}: la prima cayo {r['caida_pct']}% "
                "respecto del snapshot anterior. Analizar causas y retencion."
            )
            instruccion = "Redacta una observacion sobre un segmento en baja."
        return grounded_draft(
            accion, instruccion=instruccion, fallback=fallback, settings=self.settings
        )
