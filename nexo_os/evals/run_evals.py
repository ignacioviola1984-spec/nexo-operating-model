"""Eval / guardrail harness (§16) - the build gate. Exits non-zero on failure.

Self-contained: builds a fresh local store from the committed synthetic workbooks,
runs a full cycle offline (no API key), and asserts the non-negotiables. A red
eval is a blocker, like a failed test. Run: `make eval`.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from nexo_os import audit, auth, review
from nexo_os.agents.narrate import build_allowed, extract_numbers, numbers_in
from nexo_os.auth import AuthError
from nexo_os.config import Thresholds, reload_settings
from nexo_os.core.cartera import compute_cartera
from nexo_os.core.cobranza import compute_cobranza
from nexo_os.core.comercial import compute_comercial
from nexo_os.core.comisiones import compute_comisiones
from nexo_os.core.renovaciones import compute_renovaciones
from nexo_os.dashboard import actions
from nexo_os.data.ingest import ingest, read_workbook, validate_workbook
from nexo_os.data.schema.models import EstadoAccion, Prioridad, Rol
from nexo_os.data.snapshot_repository import SnapshotRepository
from nexo_os.orchestrator import run_cycle
from nexo_os.state import NexoContext

SYN = Path(__file__).resolve().parent.parent / "data" / "synthetic"
BROKEN = SYN / "broken"
AS_OF = date(2026, 6, 30)
AS_OF_PRIOR = date(2026, 5, 31)
NOW = datetime(2026, 6, 30, 12, 0, 0)
T = Thresholds()


def _load(
    tmp: Path, *, with_prior: bool = True, current="cartera_actual.xlsx"
) -> SnapshotRepository:
    repo = SnapshotRepository.open(tmp / "nexo.duckdb")
    if with_prior:
        ingest(
            SYN / "cartera_anterior.xlsx",
            cargado_por="admin",
            repo=repo,
            snapshot_fecha=AS_OF_PRIOR,
            now=datetime(2026, 5, 31, 9, 0, 0),
        )
    ingest(SYN / current, cargado_por="admin", repo=repo, snapshot_fecha=AS_OF, now=NOW)
    return repo


# --------------------------------------------------------------------------- #
# Evals
# --------------------------------------------------------------------------- #
def eval_ingestion_fail_closed(tmp: Path) -> None:
    repo = _load(tmp, with_prior=False)
    good = repo.active_snapshot().snapshot_id
    expected = {
        "missing_sheet.xlsx": "hoja_faltante",
        "bad_enum.xlsx": "enum",
        "broken_fk.xlsx": "fk_rota",
        "duplicate_pk.xlsx": "pk_duplicada",
        "negative_amount.xlsx": "monto_negativo",
    }
    for fixture, code in expected.items():
        report, _ = validate_workbook(read_workbook(BROKEN / fixture))
        assert not report.ok, f"{fixture} should be rejected"
        assert code in {e.codigo for e in report.errores}, f"{fixture}: missing {code}"
        # Attempting to ingest must change nothing (no partial ingest).
        result = ingest(
            BROKEN / fixture,
            cargado_por="admin",
            repo=repo,
            snapshot_fecha=date(2026, 7, 31),
            now=datetime(2026, 7, 31),
        )
        assert result.ok is False and result.snapshot is None
    assert repo.active_snapshot().snapshot_id == good
    assert len(repo.list_snapshots()) == 1
    repo.close()


def eval_numbers_regression(tmp: Path) -> None:
    repo = _load(tmp)
    car = compute_cartera(
        repo.get_polizas(),
        repo.get_clientes(),
        thresholds=T,
        prev_polizas=repo.prev_polizas(),
        prev_clientes=repo.prev_clientes(),
    )
    assert car.polizas_en_vigor == 9
    assert car.prima_total == Decimal("1000000.00")
    assert car.comision_esperada_total == Decimal("100000.00")
    assert round(car.hhi_aseguradora, 2) == 0.54
    assert [s for s, _ in car.segmentos_en_baja] == ["premium"]

    cob = compute_cobranza(
        repo.get_cuotas(), repo.get_polizas(), repo.get_clientes(), as_of=AS_OF, thresholds=T
    )
    assert cob.overdue_count == 6
    assert cob.total_overdue_ars == Decimal("190000.00")
    assert cob.bucket_counts == {"1-30": 2, "31-60": 1, "61-90": 1, "90+": 2}

    com = compute_comisiones(repo.get_comisiones(), as_of=AS_OF, thresholds=T)
    assert com.total_diferencia_ars == Decimal("20000.00")
    assert com.discrepancia_count == 3 and com.aged_count == 1

    ren = compute_renovaciones(
        repo.get_polizas(),
        repo.get_cuotas(),
        repo.get_siniestros(),
        as_of=AS_OF,
        thresholds=T,
        has_siniestros=repo.has_siniestros(),
    )
    assert (ren.expiring_30, ren.expiring_60, ren.expiring_90) == (2, 3, 4)
    assert ren.at_risk_count == 1

    comm = compute_comercial(repo.get_leads(), repo.get_cotizaciones(), as_of=AS_OF, thresholds=T)
    assert comm.weighted_forecast_ars == Decimal("185000.00")
    assert (comm.sin_cotizacion_count, comm.no_presentada_count, comm.estancado_count) == (1, 1, 1)
    repo.close()


def eval_agent_detection(tmp: Path) -> None:
    repo = _load(tmp)
    ctx = run_cycle(repo, now=NOW, run_id="EVAL")
    by_agent: dict[str, int] = {}
    for a in ctx.acciones:
        by_agent[a.agente] = by_agent.get(a.agente, 0) + 1
    assert by_agent.get("cobranza") == 6
    assert by_agent.get("renovaciones") == 4
    assert by_agent.get("comisiones") == 3
    assert by_agent.get("comercial") == 3
    assert by_agent.get("cartera") == 2
    # The planted at-risk renewal is present.
    assert any(
        a.tipo_accion == "renovacion_riesgo" and a.entidad_id == "POL-EXP-07" for a in ctx.acciones
    )
    repo.close()


def eval_grounding(tmp: Path) -> None:
    repo = _load(tmp)
    ctx = run_cycle(repo, now=NOW, run_id="EVAL")
    for a in ctx.acciones:
        allowed = build_allowed(extract_numbers(json.loads(a.rationale_json)))
        offending = [n for n in numbers_in(a.mensaje_es) if n not in allowed]
        assert offending == [], f"{a.accion_id}: ungrounded numbers {offending}"
    # Positive control: a fabricated/rounded figure must be rejected.
    from nexo_os.agents.narrate import grounding_ok

    ok, _ = grounding_ok("casi 3.999.999 en juego", [Decimal("330000")])
    assert ok is False
    repo.close()


def eval_pii_minimization(tmp: Path) -> None:
    repo = _load(tmp)
    ctx = run_cycle(repo, now=NOW, run_id="EVAL")
    for a in ctx.acciones:
        blob = a.mensaje_es + a.rationale_json
        assert "@example.com" not in blob
        assert "20-0000000" not in blob  # document prefix
        assert "+54 9 11" not in blob  # phone prefix
    repo.close()


def eval_refusal_insufficient_data(tmp: Path) -> None:
    # No prior snapshot -> growth is explicit 'sin base', not a fabricated delta.
    repo = _load(tmp, with_prior=False)
    car = compute_cartera(repo.get_polizas(), repo.get_clientes(), thresholds=T)
    assert car.sin_base_comparacion is True and car.crecimiento_prima is None
    repo.close()
    # No siniestros sheet -> risk computed without it and labeled.
    repo2 = SnapshotRepository.open(tmp / "nosin.duckdb")
    ingest(
        SYN / "cartera_sin_siniestros.xlsx",
        cargado_por="admin",
        repo=repo2,
        snapshot_fecha=AS_OF,
        now=NOW,
    )
    ren = compute_renovaciones(
        repo2.get_polizas(),
        repo2.get_cuotas(),
        repo2.get_siniestros(),
        as_of=AS_OF,
        thresholds=T,
        has_siniestros=repo2.has_siniestros(),
    )
    assert ren.usa_siniestros is False
    repo2.close()


def eval_reconciliation(tmp: Path) -> None:
    repo = _load(tmp)
    ctx = run_cycle(repo, now=NOW, run_id="EVAL")
    assert ctx.escalaciones == [], f"reconciliation breaks: {ctx.escalaciones}"
    repo.close()


def eval_audit_integrity(tmp: Path) -> None:
    repo = _load(tmp)
    ctx = run_cycle(repo, now=NOW, run_id="EVAL")
    # Resolve one action, then verify the chain is intact.
    accion = repo.list_acciones(estado=EstadoAccion.propuesta)[0]
    auth.create_user(repo, usuario="op", nombre="Op", rol=Rol.operador, password="pw", now=NOW)
    review.approve(repo, accion.accion_id, by="op", now=NOW, nota="ok")
    ok, bad = audit.verify_chain(repo)
    assert ok, f"audit chain broken at {bad}"
    assert len(ctx.acciones) > 0
    repo.close()


def eval_rbac_boundary(tmp: Path) -> None:
    repo = _load(tmp)
    # Seed an action + an operador session.
    op = auth.create_user(repo, usuario="op", nombre="Op", rol=Rol.operador, password="pw", now=NOW)
    op_sess = auth.new_session(op, now=NOW, ttl_minutes=480)
    snap = repo.active_snapshot()
    from nexo_os.agents.base import build_accion

    ctx = NexoContext(
        repo, run_id="RB", snapshot_id=snap.snapshot_id, snapshot_fecha=snap.snapshot_fecha, now=NOW
    )
    a = build_accion(
        ctx,
        agente="cobranza",
        tipo_accion="t",
        entidad_tipo="cuota",
        entidad_id="Q",
        prioridad=Prioridad.alta,
        confianza=0.9,
        monto_en_juego_ars=None,
        rationale={},
        mensaje_es="x",
    )
    ctx.add_accion(a)

    # Upload requires admin: operador and unauthenticated must be rejected.
    for sess in (op_sess, None):
        try:
            actions.do_upload(
                repo, sess, SYN / "cartera_actual.xlsx", snapshot_fecha=AS_OF, now=NOW
            )
            raise AssertionError("upload should be admin-only")
        except AuthError:
            pass
    # Review requires authentication: unauthenticated must be rejected.
    for fn in (actions.do_approve, actions.do_reject):
        try:
            fn(repo, None, a.accion_id, now=NOW)
            raise AssertionError("review should require authentication")
        except AuthError:
            pass
    repo.close()


EVALS = [
    ("ingestion_fail_closed", eval_ingestion_fail_closed),
    ("numbers_regression", eval_numbers_regression),
    ("agent_detection", eval_agent_detection),
    ("grounding_guardrail", eval_grounding),
    ("pii_minimization", eval_pii_minimization),
    ("refusal_insufficient_data", eval_refusal_insufficient_data),
    ("reconciliation", eval_reconciliation),
    ("audit_integrity", eval_audit_integrity),
    ("auth_rbac_boundary", eval_rbac_boundary),
]


def main() -> int:
    settings = reload_settings()
    mode = "LLM (Claude)" if settings.llm_enabled else "offline (plantillas)"
    print(f"Modo de prosa: {mode}  [grounding_guardrail valida la salida real en ambos]")
    results = []
    for name, fn in EVALS:
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                results.append((name, True, ""))
            except Exception as exc:  # noqa: BLE001 - eval harness reports all failures
                results.append((name, False, f"{type(exc).__name__}: {exc}"))

    print("=" * 60)
    print("NEXO EVALS")
    print("=" * 60)
    failed = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f"  -> {detail}" if not ok else ""))
        failed += 0 if ok else 1
    print("-" * 60)
    print(f"{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
