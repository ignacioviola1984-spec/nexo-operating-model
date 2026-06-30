"""Phase 5: the five agents surface their planted situations with the expected
figures, deterministic confidence/priority, grounded prose, and minimized PII."""

from __future__ import annotations

import json
from datetime import datetime

from nexo_os.agents.base import Agent
from nexo_os.agents.cartera_agent import CarteraAgent
from nexo_os.agents.cobranza_agent import CobranzaAgent
from nexo_os.agents.comercial_agent import ComercialAgent
from nexo_os.agents.comisiones_agent import ComisionesAgent
from nexo_os.agents.narrate import build_allowed, extract_numbers, numbers_in
from nexo_os.agents.renovaciones_agent import RenovacionesAgent
from nexo_os.config import Thresholds, reload_settings
from nexo_os.data.schema.models import EstadoAccion, Prioridad
from nexo_os.state import NexoContext

T = Thresholds()
NOW = datetime(2026, 6, 30, 12, 0, 0)


def _ctx(repo):
    snap = repo.active_snapshot()
    return NexoContext(
        repo,
        run_id="RUN1",
        snapshot_id=snap.snapshot_id,
        snapshot_fecha=snap.snapshot_fecha,
        now=NOW,
    )


def _run(agent: Agent, repo):
    settings = reload_settings()  # offline (NEXO_USE_LLM unset)
    agent.settings = settings
    ctx = _ctx(repo)
    agent.run(ctx)
    return ctx


def _assert_grounded(acciones):
    for a in acciones:
        allowed = build_allowed(extract_numbers(json.loads(a.rationale_json)))
        offending = [n for n in numbers_in(a.mensaje_es) if n not in allowed]
        assert offending == [], f"{a.accion_id}: {offending} not in rationale ({a.mensaje_es})"


def test_cobranza_agent_surfaces_all_overdue(loaded_repo):
    ctx = _run(CobranzaAgent(T), loaded_repo)
    assert len(ctx.acciones) == 6
    assert all(a.tipo_accion == "gestion_cobranza" for a in ctx.acciones)
    # The two 90+ items are high priority; amounts match outstanding.
    altas = [a for a in ctx.acciones if a.prioridad == Prioridad.alta]
    assert len(altas) == 2
    assert {int(a.monto_en_juego_ars) for a in altas} == {50000}
    _assert_grounded(ctx.acciones)


def test_renovaciones_agent_flags_at_risk(loaded_repo):
    ctx = _run(RenovacionesAgent(T), loaded_repo)
    assert len(ctx.acciones) == 4  # expiring within 90d
    riesgo = [a for a in ctx.acciones if a.tipo_accion == "renovacion_riesgo"]
    assert len(riesgo) == 1
    assert riesgo[0].entidad_id == "POL-EXP-07"
    assert json.loads(riesgo[0].rationale_json)["en_riesgo"] is True
    _assert_grounded(ctx.acciones)


def test_cartera_agent_concentration_and_shrinking_segment(loaded_repo):
    ctx = _run(CarteraAgent(T), loaded_repo)
    tipos = {a.tipo_accion for a in ctx.acciones}
    assert "revisar_concentracion" in tipos
    assert "revisar_segmento" in tipos
    conc = next(a for a in ctx.acciones if a.tipo_accion == "revisar_concentracion")
    assert conc.entidad_id == "A1"
    assert conc.monto_en_juego_ars is None  # informational, no amount invented
    seg = next(a for a in ctx.acciones if a.tipo_accion == "revisar_segmento")
    assert seg.entidad_id == "premium"
    assert json.loads(seg.rationale_json)["caida_pct"] == 10
    _assert_grounded(ctx.acciones)


def test_comisiones_agent_disputes_discrepancies(loaded_repo):
    ctx = _run(ComisionesAgent(T), loaded_repo)
    assert len(ctx.acciones) == 3
    assert all(a.tipo_accion == "reclamo_comision" for a in ctx.acciones)
    montos = sorted(int(a.monto_en_juego_ars) for a in ctx.acciones)
    assert montos == [5000, 5000, 10000]
    _assert_grounded(ctx.acciones)


def test_comercial_agent_funnel_flags(loaded_repo):
    ctx = _run(ComercialAgent(T), loaded_repo)
    tipos = sorted(a.tipo_accion for a in ctx.acciones)
    assert tipos == ["funnel_estancado", "funnel_no_presentada", "funnel_sin_cotizacion"]
    # No natural amount -> all null; priority comes from urgency only.
    assert all(a.monto_en_juego_ars is None for a in ctx.acciones)
    _assert_grounded(ctx.acciones)


def test_agents_persist_and_audit(loaded_repo):
    from nexo_os import audit

    _run(CobranzaAgent(T), loaded_repo)
    # Persisted as 'propuesta' and the audit chain is intact after proposing.
    propuestas = loaded_repo.list_acciones(estado=EstadoAccion.propuesta)
    assert len(propuestas) == 6
    assert audit.verify_chain(loaded_repo)[0] is True


def test_pii_minimization_in_messages(loaded_repo):
    # narrate inputs/messages must not carry full documento/email/telefono.
    for agent in (CobranzaAgent(T), RenovacionesAgent(T), ComercialAgent(T)):
        ctx = _run(agent, loaded_repo)
        for a in ctx.acciones:
            blob = a.mensaje_es + a.rationale_json
            assert "@example.com" not in blob
            assert "20-0000000" not in blob  # document prefix
            assert "+54 9 11" not in blob  # phone prefix
