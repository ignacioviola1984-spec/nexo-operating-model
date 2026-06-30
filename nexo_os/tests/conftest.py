"""Shared fixtures: a repository loaded with the synthetic prior+current snapshots."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from nexo_os.data.ingest import ingest
from nexo_os.data.snapshot_repository import SnapshotRepository

SYN = Path(__file__).resolve().parent.parent / "data" / "synthetic"
AS_OF = date(2026, 6, 30)
AS_OF_PRIOR = date(2026, 5, 31)


@pytest.fixture()
def loaded_repo(tmp_path):
    """Ingest the prior then the current synthetic workbook; yield the repo."""
    repo = SnapshotRepository.open(tmp_path / "nexo.duckdb")
    ingest(
        SYN / "cartera_anterior.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=AS_OF_PRIOR,
        now=datetime(2026, 5, 31, 9, 0, 0),
    )
    ingest(
        SYN / "cartera_actual.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=AS_OF,
        now=datetime(2026, 6, 30, 9, 0, 0),
    )
    yield repo
    repo.close()


@pytest.fixture()
def current_only_repo(tmp_path):
    """Ingest only the current workbook (no prior snapshot)."""
    repo = SnapshotRepository.open(tmp_path / "nexo.duckdb")
    ingest(
        SYN / "cartera_actual.xlsx",
        cargado_por="admin",
        repo=repo,
        snapshot_fecha=AS_OF,
        now=datetime(2026, 6, 30, 9, 0, 0),
    )
    yield repo
    repo.close()
