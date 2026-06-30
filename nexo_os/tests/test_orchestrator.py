"""Phase 6: the full orchestrator cycle - compute -> reconcile -> propose ->
narrate -> persist, with run status and a verifiable audit chain."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from nexo_os import audit
from nexo_os.data.ingest import ingest
from nexo_os.data.schema.models import EstadoAccion, EstadoRun
from nexo_os.data.snapshot_repository import SnapshotRepository
from nexo_os.orchestrator import run_cycle
from nexo_os.tests.conftest import SYN

NOW = datetime(2026, 6, 30, 12, 0, 0)


def _fresh_loaded(tmp_path, name):
    repo = SnapshotRepository.open(tmp_path / f"{name}.duckdb")
    ingest(
        SYN / "cartera_anterior.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=date(2026, 5, 31),
        now=datetime(2026, 5, 31, 9, 0, 0),
    )
    ingest(
        SYN / "cartera_actual.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=date(2026, 6, 30),
        now=datetime(2026, 6, 30, 9, 0, 0),
    )
    return repo


def test_full_cycle_proposes_and_persists(loaded_repo):
    ctx = run_cycle(loaded_repo, now=NOW, run_id="RUN-T")
    # 6 cobranza + 4 renovaciones + 3 comisiones + 2 cartera + 3 comercial = 18
    assert len(ctx.acciones) == 18
    assert len(loaded_repo.list_acciones(estado=EstadoAccion.propuesta)) == 18


def test_cycle_run_status_ok_and_reconciles(loaded_repo):
    ctx = run_cycle(loaded_repo, now=NOW, run_id="RUN-T")
    assert ctx.escalaciones == []  # reconciliations tie on synthetic data
    # Run row persisted as ok.
    row = loaded_repo.con.execute(
        "SELECT estado, resumen_json FROM agent_runs WHERE run_id = ?", ["RUN-T"]
    ).fetchone()
    assert row[0] == EstadoRun.ok.value
    assert '"acciones_total": 18' in row[1]


def test_cycle_audit_chain_intact_with_run_markers(loaded_repo):
    run_cycle(loaded_repo, now=NOW, run_id="RUN-T")
    ok, _ = audit.verify_chain(loaded_repo)
    assert ok is True
    acciones_log = {e.accion for e in loaded_repo.read_audit()}
    assert {"run_start", "run_end", "propose"} <= acciones_log


def test_cycle_requires_active_snapshot(tmp_path):
    repo = SnapshotRepository.open(tmp_path / "empty.duckdb")
    try:
        with pytest.raises(RuntimeError):
            run_cycle(repo, now=NOW)
    finally:
        repo.close()


def test_cycle_is_deterministic(tmp_path):
    r1 = _fresh_loaded(tmp_path, "a")
    r2 = _fresh_loaded(tmp_path, "b")
    try:
        c1 = run_cycle(r1, now=NOW, run_id="RUN-X")
        c2 = run_cycle(r2, now=NOW, run_id="RUN-X")

        def key(a):
            return (a.accion_id, a.prioridad.value, str(a.monto_en_juego_ars), a.confianza)

        assert sorted(map(key, c1.acciones)) == sorted(map(key, c2.acciones))
    finally:
        r1.close()
        r2.close()
