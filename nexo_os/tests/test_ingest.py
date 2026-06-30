"""Phase 2: fail-closed ingestion. Valid -> snapshot; broken -> whole rejection,
prior snapshot untouched, NO partial ingest ever."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from nexo_os.data.ingest import ingest, read_workbook, validate_workbook
from nexo_os.data.snapshot_repository import SnapshotRepository

SYN = Path(__file__).resolve().parent.parent / "data" / "synthetic"
BROKEN = SYN / "broken"
AS_OF = date(2026, 6, 30)
AS_OF_PRIOR = date(2026, 5, 31)
NOW = datetime(2026, 6, 30, 9, 0, 0)


@pytest.fixture()
def repo(tmp_path):
    r = SnapshotRepository.open(tmp_path / "nexo.duckdb")
    yield r
    r.close()


def test_valid_current_workbook_validates():
    report, typed = validate_workbook(read_workbook(SYN / "cartera_actual.xlsx"))
    assert report.ok, report.render_es()
    assert report.row_counts == {
        "clientes": 11,
        "polizas": 12,
        "cuotas": 9,
        "comisiones": 10,
        "leads": 6,
        "cotizaciones": 3,
        "aseguradoras": 3,
        "productores": 2,
        "siniestros": 1,
    }


def test_valid_workbook_ingests_to_active_snapshot(repo):
    result = ingest(
        SYN / "cartera_actual.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=AS_OF,
        now=NOW,
    )
    assert result.ok
    assert "VALIDACION OK" in result.report.render_es()
    snap = repo.active_snapshot()
    assert snap is not None and snap.snapshot_fecha == AS_OF
    assert len(repo.get_polizas()) == 12
    assert repo.has_siniestros() is True


def test_prior_then_current_gives_previous_snapshot(repo):
    ingest(
        SYN / "cartera_anterior.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=AS_OF_PRIOR,
        now=datetime(2026, 5, 31, 9, 0, 0),
    )
    ingest(
        SYN / "cartera_actual.xlsx", cargado_por="admin", repo=repo, snapshot_fecha=AS_OF, now=NOW
    )
    assert repo.active_snapshot().snapshot_fecha == AS_OF
    prev = repo.get_previous_snapshot()
    assert prev is not None and prev.snapshot_fecha == AS_OF_PRIOR


def test_sin_siniestros_is_valid_and_degrades(repo):
    result = ingest(
        SYN / "cartera_sin_siniestros.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=AS_OF,
        now=NOW,
    )
    assert result.ok
    assert repo.has_siniestros() is False
    assert repo.get_siniestros() == []


@pytest.mark.parametrize(
    "fixture,code",
    [
        ("missing_sheet.xlsx", "hoja_faltante"),
        ("bad_enum.xlsx", "enum"),
        ("broken_fk.xlsx", "fk_rota"),
        ("duplicate_pk.xlsx", "pk_duplicada"),
        ("negative_amount.xlsx", "monto_negativo"),
    ],
)
def test_broken_workbook_rejected_with_expected_code(fixture, code):
    report, _ = validate_workbook(read_workbook(BROKEN / fixture))
    assert not report.ok
    assert code in {e.codigo for e in report.errores}
    assert "RECHAZADO" in report.render_es()


@pytest.mark.parametrize(
    "fixture",
    [
        "missing_sheet.xlsx",
        "bad_enum.xlsx",
        "broken_fk.xlsx",
        "duplicate_pk.xlsx",
        "negative_amount.xlsx",
    ],
)
def test_broken_upload_never_partially_ingests(repo, fixture):
    # Establish a known-good active snapshot first.
    ingest(
        SYN / "cartera_actual.xlsx", cargado_por="admin", repo=repo, snapshot_fecha=AS_OF, now=NOW
    )
    good_id = repo.active_snapshot().snapshot_id
    good_polizas = len(repo.get_polizas())

    # A broken upload must change nothing.
    result = ingest(
        BROKEN / fixture,
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=date(2026, 7, 31),
        now=datetime(2026, 7, 31, 9, 0, 0),
    )
    assert result.ok is False
    assert result.snapshot is None
    assert repo.active_snapshot().snapshot_id == good_id  # prior snapshot intact
    assert len(repo.get_polizas()) == good_polizas
    # No leaked rows: the store still holds exactly one snapshot.
    assert len(repo.list_snapshots()) == 1


def test_ingest_is_atomic_under_store_inspection(repo, tmp_path):
    # After a rejected upload, exactly one snapshot row exists (the good one).
    ingest(
        SYN / "cartera_actual.xlsx", cargado_por="admin", repo=repo, snapshot_fecha=AS_OF, now=NOW
    )
    ingest(
        BROKEN / "bad_enum.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=date(2026, 7, 31),
        now=datetime(2026, 7, 31, 9, 0, 0),
    )
    snaps = repo.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0].snapshot_fecha == AS_OF
