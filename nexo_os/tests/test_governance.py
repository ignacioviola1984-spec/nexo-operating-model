"""Phase 4: governance - audit hash chain, maker-checker, scoring, grounding
guard, reconciliation, execution seam, PII redaction."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest

from nexo_os import audit, pii, review
from nexo_os.agents import scoring
from nexo_os.agents.base import build_accion
from nexo_os.agents.narrate import draft, grounding_ok, numbers_in
from nexo_os.config import Thresholds, reload_settings
from nexo_os.data.schema.models import EstadoAccion, Prioridad
from nexo_os.execution import NoopExecutionAdapter
from nexo_os.reliability import reconcile
from nexo_os.state import NexoContext

T = Thresholds()
NOW = datetime(2026, 6, 30, 12, 0, 0)


# --------------------------- audit chain ------------------------------------ #
def test_audit_chain_records_and_verifies(current_only_repo):
    repo = current_only_repo
    audit.record_event(repo, actor="admin", accion="upload", ts=NOW, detalle={"x": 1})
    audit.record_event(repo, actor="op", accion="approve", ts=NOW, entidad_id="A1", detalle={})
    ok, bad = audit.verify_chain(repo)
    assert ok is True and bad is None
    events = repo.read_audit()
    assert events[0].prev_hash is None
    assert events[1].prev_hash == events[0].hash


def test_audit_chain_detects_tampering(current_only_repo):
    repo = current_only_repo
    audit.record_event(repo, actor="admin", accion="upload", ts=NOW, detalle={"x": 1})
    audit.record_event(repo, actor="op", accion="approve", ts=NOW, detalle={"y": 2})
    # Tamper directly in the store (bypassing the append-only writer).
    repo.con.execute(
        "UPDATE audit_log SET detalle_json = ? WHERE evento_id = ?", ['{"x": 999}', "EVT-00000001"]
    )
    ok, bad = audit.verify_chain(repo)
    assert ok is False
    assert bad == 0


# --------------------------- maker-checker ---------------------------------- #
def _ctx(repo):
    snap = repo.active_snapshot()
    return NexoContext(
        repo,
        run_id="RUN1",
        snapshot_id=snap.snapshot_id,
        snapshot_fecha=snap.snapshot_fecha,
        now=NOW,
    )


def _propose_one(ctx):
    accion = build_accion(
        ctx,
        agente="cobranza",
        tipo_accion="gestion_cobranza",
        entidad_tipo="cuota",
        entidad_id="Q-90-a",
        prioridad=Prioridad.alta,
        confianza=0.9,
        monto_en_juego_ars=Decimal("50000.00"),
        rationale={"monto": "50000.00", "dias": 171},
        mensaje_es="Propuesta.",
    )
    ctx.add_accion(accion)
    return accion


def test_approve_records_decision(current_only_repo):
    ctx = _ctx(current_only_repo)
    accion = _propose_one(ctx)
    resolved = review.approve(
        current_only_repo, accion.accion_id, by="operador1", now=NOW, nota="ok"
    )
    assert resolved.estado == EstadoAccion.aprobada
    assert resolved.resuelta_por == "operador1"
    # Re-resolving a resolved action is rejected.
    with pytest.raises(review.ReviewError):
        review.approve(current_only_repo, accion.accion_id, by="x", now=NOW)


def test_edit_changes_message_and_marks_editada(current_only_repo):
    ctx = _ctx(current_only_repo)
    accion = _propose_one(ctx)
    resolved = review.edit(
        current_only_repo, accion.accion_id, "Mensaje editado.", by="op", now=NOW
    )
    assert resolved.estado == EstadoAccion.editada
    assert resolved.mensaje_es == "Mensaje editado."


def test_reject_records_and_audits(current_only_repo):
    ctx = _ctx(current_only_repo)
    accion = _propose_one(ctx)
    review.reject(current_only_repo, accion.accion_id, by="op", now=NOW, nota="no aplica")
    assert current_only_repo.get_accion(accion.accion_id).estado == EstadoAccion.rechazada
    # propose + reject both audited; chain still intact.
    assert audit.verify_chain(current_only_repo)[0] is True


# --------------------------- scoring ---------------------------------------- #
def test_confidence_is_weighted_and_bounded():
    assert scoring.confidence(1.0, 1.0, T) == 1.0
    assert scoring.confidence(0.0, 0.0, T) == 0.0
    assert scoring.confidence(2.0, -1.0, T) == round(T.conf_weight_data, 4)  # clamped


def test_priority_amount_and_urgency():
    assert scoring.priority(Decimal("250000"), None, T) == Prioridad.alta
    assert scoring.priority(Decimal("60000"), None, T) == Prioridad.media
    assert scoring.priority(Decimal("100"), None, T) == Prioridad.baja
    # Takes the more severe of amount/urgency.
    assert scoring.priority(Decimal("100"), Prioridad.alta, T) == Prioridad.alta


def test_priority_null_amount_uses_urgency_only():
    assert scoring.priority(None, Prioridad.alta, T) == Prioridad.alta
    assert scoring.priority(None, None, T) == Prioridad.baja  # never invents an amount


# --------------------------- grounding guard -------------------------------- #
def test_numbers_in_normalizes_separators():
    assert "330000" in numbers_in("Vencen por ARS 330.000 en total")
    assert numbers_in("sin numeros") == set()


def test_grounding_accepts_grounded_and_rejects_fabricated():
    allowed = [4, Decimal("330000.00"), 90]
    ok, off = grounding_ok("Vencen 4 polizas por 330.000 en 90 dias.", allowed)
    assert ok is True and off == []
    ok, off = grounding_ok("Son casi 3.999.999 en juego.", allowed)
    assert ok is False and "3999999" in off


def test_draft_offline_uses_template(monkeypatch):
    monkeypatch.setenv("NEXO_USE_LLM", "0")
    reload_settings()
    out = draft(system="s", prompt="p", allowed_values=[4], fallback="Plantilla.")
    assert out == {"text": "Plantilla.", "source": "template"}
    reload_settings()


# --------------------------- reconciliation --------------------------------- #
def _core_results(repo):
    from nexo_os.core.cartera import compute_cartera
    from nexo_os.core.cobranza import compute_cobranza
    from nexo_os.core.comisiones import compute_comisiones
    from nexo_os.core.renovaciones import compute_renovaciones

    as_of = repo.snapshot_fecha
    car = compute_cartera(repo.get_polizas(), repo.get_clientes(), thresholds=T)
    com = compute_comisiones(repo.get_comisiones(), as_of=as_of, thresholds=T)
    cob = compute_cobranza(
        repo.get_cuotas(), repo.get_polizas(), repo.get_clientes(), as_of=as_of, thresholds=T
    )
    ren = compute_renovaciones(
        repo.get_polizas(),
        repo.get_cuotas(),
        repo.get_siniestros(),
        as_of=as_of,
        thresholds=T,
        has_siniestros=repo.has_siniestros(),
    )
    return car, com, cob, ren


def test_reconciliation_ties_on_synthetic(current_only_repo):
    car, com, cob, ren = _core_results(current_only_repo)
    checks = reconcile(car, com, cob, ren, thresholds=T)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_reconciliation_detects_break(current_only_repo):
    car, com, cob, ren = _core_results(current_only_repo)
    broken = dataclasses.replace(car, prima_total=Decimal("999.99"))  # break the tie
    checks = reconcile(broken, com, cob, ren, thresholds=T)
    failed = [c for c in checks if not c.ok]
    assert any(c.nombre == "cartera_premium_vs_comisiones_base" for c in failed)


# --------------------------- execution seam --------------------------------- #
def test_noop_execution_sends_nothing(current_only_repo):
    ctx = _ctx(current_only_repo)
    accion = _propose_one(ctx)
    adapter = NoopExecutionAdapter()
    assert adapter.enabled is False
    assert adapter.execute(current_only_repo, accion, now=NOW) == "noop"
    # Records a 'would_execute' note; chain intact.
    assert any(e.accion == "would_execute" for e in current_only_repo.read_audit())


# --------------------------- PII redaction ---------------------------------- #
def test_pii_helpers_minimize():
    assert pii.first_name("Ana Ficticia C01") == "Ana"
    assert pii.mask_document("20-12345678-9").endswith("-9")
    assert "12345678" not in pii.mask_document("20-12345678-9")
    assert pii.safe_lead_label("Prospecto Falso", "L01") == "Prospecto (L01)"
