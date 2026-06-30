"""Orchestrator (§11): one full cycle against the active snapshot.

load repository -> each agent compute -> deterministic cross-checks/reconciliations
-> propose -> narrate (grounded) -> persist acciones, agent_runs, audit_log ->
return the populated NexoContext. Run status: ok | con_warnings | error. Fails
closed: on an agent error the run reports error rather than emitting partial
numbers as complete.
"""

from __future__ import annotations

import json
from datetime import datetime

from nexo_os import audit
from nexo_os.agents.base import Agent
from nexo_os.agents.cartera_agent import CarteraAgent
from nexo_os.agents.cobranza_agent import CobranzaAgent
from nexo_os.agents.comercial_agent import ComercialAgent
from nexo_os.agents.comisiones_agent import ComisionesAgent
from nexo_os.agents.renovaciones_agent import RenovacionesAgent
from nexo_os.config import Settings, get_settings
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import AgentRun, EstadoRun
from nexo_os.logging import bind_run_id, get_logger
from nexo_os.reliability import reconcile
from nexo_os.state import NexoContext

log = get_logger(__name__)


def _build_agents(settings: Settings) -> list[Agent]:
    """High-action agents first (Cobranza, Renovaciones), then the rest."""
    t = settings.thresholds
    return [
        CobranzaAgent(t, settings),
        RenovacionesAgent(t, settings),
        ComisionesAgent(t, settings),
        CarteraAgent(t, settings),
        ComercialAgent(t, settings),
    ]


def _resumen(ctx: NexoContext, recon_ok: bool) -> dict:
    by_prioridad: dict[str, int] = {}
    for a in ctx.acciones:
        by_prioridad[a.prioridad.value] = by_prioridad.get(a.prioridad.value, 0) + 1
    return {
        "acciones_total": len(ctx.acciones),
        "acciones_por_prioridad": by_prioridad,
        "escalaciones": len(ctx.escalaciones),
        "reconciliacion_ok": recon_ok,
    }


def run_cycle(
    repo: NexoRepository,
    *,
    now: datetime,
    settings: Settings | None = None,
    run_id: str | None = None,
) -> NexoContext:
    """Run a full agent cycle. Requires an active snapshot (fails closed otherwise)."""
    settings = settings or get_settings()
    snap = repo.active_snapshot()
    if snap is None:
        raise RuntimeError("No hay snapshot activo: no se puede correr el ciclo.")

    run_id = run_id or f"run-{snap.snapshot_id}-{now:%Y%m%d%H%M%S}"
    bind_run_id(run_id)
    ctx = NexoContext(
        repo,
        run_id=run_id,
        snapshot_id=snap.snapshot_id,
        snapshot_fecha=snap.snapshot_fecha,
        now=now,
    )

    run = AgentRun(
        run_id=run_id,
        iniciado_en=now,
        estado=EstadoRun.ok,
        resumen_json="{}",
        snapshot_id=snap.snapshot_id,
    )
    repo.add_run(run)
    audit.record_event(
        repo,
        actor="orchestrator",
        accion="run_start",
        ts=now,
        detalle={"run_id": run_id, "snapshot_id": snap.snapshot_id},
    )
    log.info("run_start", snapshot_id=snap.snapshot_id, snapshot_fecha=str(snap.snapshot_fecha))

    try:
        for agent in _build_agents(settings):
            agent.run(ctx)

        # Deterministic cross-checks/reconciliations (§10/§11).
        checks = reconcile(
            ctx.get_result("cartera"),
            ctx.get_result("comisiones"),
            ctx.get_result("cobranza"),
            ctx.get_result("renovaciones"),
            thresholds=settings.thresholds,
        )
        recon_ok = all(c.ok for c in checks)
        for c in checks:
            if not c.ok:
                ctx.escalate(c.severidad, c.nombre, c.detalle)

        estado = EstadoRun.con_warnings if ctx.escalaciones else EstadoRun.ok
        run.estado = estado
        run.finalizado_en = now
        run.resumen_json = json.dumps(_resumen(ctx, recon_ok), ensure_ascii=False)
        repo.update_run(run)
        audit.record_event(
            repo,
            actor="orchestrator",
            accion="run_end",
            ts=now,
            detalle={"run_id": run_id, "estado": estado.value, "acciones": len(ctx.acciones)},
        )
        log.info(
            "run_end",
            estado=estado.value,
            acciones=len(ctx.acciones),
            escalaciones=len(ctx.escalaciones),
        )
        return ctx
    except Exception as exc:  # fail closed: report error, do not emit partials as complete
        run.estado = EstadoRun.error
        run.finalizado_en = now
        run.resumen_json = json.dumps({"error": type(exc).__name__}, ensure_ascii=False)
        repo.update_run(run)
        audit.record_event(
            repo,
            actor="orchestrator",
            accion="run_error",
            ts=now,
            detalle={"run_id": run_id, "error": type(exc).__name__},
        )
        log.error("run_error", error=type(exc).__name__)
        raise
