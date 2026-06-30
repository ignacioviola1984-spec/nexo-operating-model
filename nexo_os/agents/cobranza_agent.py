"""Cobranza y morosidad agent (collections + delinquency).

High action volume: one prioritized collection action per overdue installment,
highest recoverable first. Figures via core; message via the grounded prose layer.
"""

from __future__ import annotations

from nexo_os.agents import scoring
from nexo_os.agents.base import Agent, build_accion, grounded_draft
from nexo_os.config import Settings, Thresholds, get_settings
from nexo_os.core.cobranza import CobranzaResult, compute_cobranza
from nexo_os.pii import first_name
from nexo_os.state import NexoContext

_BUCKET_SIGNAL = {"1-30": 0.60, "31-60": 0.75, "61-90": 0.85, "90+": 0.95}


class CobranzaAgent(Agent):
    nombre = "cobranza"

    def __init__(self, thresholds: Thresholds, settings: Settings | None = None):
        self.thresholds = thresholds
        self.settings = settings or get_settings()

    def compute(self, ctx: NexoContext) -> CobranzaResult:
        repo = ctx.repo
        prev_snap = repo.get_previous_snapshot()
        return compute_cobranza(
            repo.get_cuotas(),
            repo.get_polizas(),
            repo.get_clientes(),
            as_of=ctx.snapshot_fecha,
            thresholds=self.thresholds,
            prev_cuotas=repo.prev_cuotas() if prev_snap else None,
            prev_as_of=prev_snap.snapshot_fecha if prev_snap else None,
        )

    def propose(self, ctx: NexoContext, result: CobranzaResult):
        name_by_id = {c.cliente_id: first_name(c.nombre) for c in ctx.repo.get_clientes()}
        acciones = []
        for it in result.items:
            cliente = name_by_id.get(it.cliente_id or "", "el cliente")
            saldo = int(it.outstanding_ars)
            signal = _BUCKET_SIGNAL.get(it.bucket, 0.6)
            data_ok = scoring.completeness([bool(it.cliente_id), saldo > 0, it.dias_mora > 0])
            conf = scoring.confidence(data_ok, signal, self.thresholds)
            prioridad = scoring.priority(
                it.outstanding_ars,
                scoring.urgency_from_age(it.dias_mora, self.thresholds),
                self.thresholds,
            )
            rationale = {
                "cliente": cliente,
                "saldo_ars": saldo,
                "dias_mora": it.dias_mora,
                "bucket": it.bucket,
            }
            acciones.append(
                build_accion(
                    ctx,
                    agente=self.nombre,
                    tipo_accion="gestion_cobranza",
                    entidad_tipo="cuota",
                    entidad_id=it.cuota_id,
                    prioridad=prioridad,
                    confianza=conf,
                    monto_en_juego_ars=it.outstanding_ars,
                    rationale=rationale,
                )
            )
        return acciones

    def narrate(self, ctx: NexoContext, result: CobranzaResult, accion):
        import json

        r = json.loads(accion.rationale_json)
        fallback = (
            f"Gestionar la cobranza de {r['cliente']}: saldo impago de ARS {r['saldo_ars']} "
            f"con {r['dias_mora']} dias de mora. Priorizar el contacto para regularizar."
        )
        return grounded_draft(
            accion,
            instruccion="Redacta una gestion de cobranza cordial pero firme para el cliente.",
            fallback=fallback,
            settings=self.settings,
        )
