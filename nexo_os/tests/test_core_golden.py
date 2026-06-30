"""Phase 3 golden tests: core figures match GROUND_TRUTH.md exactly.

Any drift here fails the build (numbers-regression). Values are asserted against
the synthetic dataset loaded through the real ingestion + repository path.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from nexo_os.config import Thresholds
from nexo_os.core.cartera import compute_cartera
from nexo_os.core.cobranza import compute_cobranza
from nexo_os.core.comercial import compute_comercial
from nexo_os.core.comisiones import compute_comisiones
from nexo_os.core.renovaciones import compute_renovaciones

T = Thresholds()


def test_cartera_golden(loaded_repo):
    r = compute_cartera(
        loaded_repo.get_polizas(),
        loaded_repo.get_clientes(),
        thresholds=T,
        prev_polizas=loaded_repo.prev_polizas(),
        prev_clientes=loaded_repo.prev_clientes(),
    )
    assert r.polizas_en_vigor == 9
    assert r.prima_total == Decimal("1000000.00")
    assert r.comision_esperada_total == Decimal("100000.00")
    assert r.mix_aseguradora["A1"] == Decimal("700000.00")
    assert r.hhi_aseguradora == pytest.approx(0.54)
    assert r.aseguradora_dominante == "A1"
    assert r.share_dominante == pytest.approx(0.70)
    assert r.concentracion_alerta is True
    assert r.prima_por_segmento["premium"] == Decimal("450000.00")
    assert r.prima_por_segmento["estandar"] == Decimal("550000.00")
    assert r.crecimiento_prima == pytest.approx(0.111111, abs=1e-5)
    assert [s for s, _ in r.segmentos_en_baja] == ["premium"]


def test_cartera_no_prior_is_sin_base(current_only_repo):
    r = compute_cartera(
        current_only_repo.get_polizas(),
        current_only_repo.get_clientes(),
        thresholds=T,
        prev_polizas=None,
        prev_clientes=None,
    )
    assert r.sin_base_comparacion is True
    assert r.crecimiento_prima is None
    assert r.segmentos_en_baja == []


def test_cobranza_golden(loaded_repo):
    r = compute_cobranza(
        loaded_repo.get_cuotas(),
        loaded_repo.get_polizas(),
        loaded_repo.get_clientes(),
        as_of=loaded_repo.snapshot_fecha,
        thresholds=T,
    )
    assert r.overdue_count == 6
    assert r.total_overdue_ars == Decimal("190000.00")
    assert r.total_receivable_ars == Decimal("215000.00")
    assert r.delinquency_rate == pytest.approx(190000 / 215000, abs=1e-6)
    assert r.dias_mora_promedio_ponderado == pytest.approx(114.32, abs=0.01)
    assert r.bucket_counts == {"1-30": 2, "31-60": 1, "61-90": 1, "90+": 2}
    assert r.bucket_ars["90+"] == Decimal("100000.00")
    # Bucket ARS sums to the overdue total (internal consistency).
    assert sum(r.bucket_ars.values()) == r.total_overdue_ars
    # Highest recovery priority is the premium-segment 90+ item.
    assert r.items[0].cuota_id == "Q-90-a"


def test_comisiones_golden(loaded_repo):
    r = compute_comisiones(
        loaded_repo.get_comisiones(), as_of=loaded_repo.snapshot_fecha, thresholds=T
    )
    assert r.total_esperada_ars == Decimal("105000.00")
    assert r.total_liquidada_ars == Decimal("85000.00")
    assert r.total_diferencia_ars == Decimal("20000.00")
    assert r.discrepancia_count == 3
    assert r.aged_count == 1
    assert r.aged_ars == Decimal("5000.00")
    assert r.aged_receivables[0].comision_id == "CM-OLD"
    # Reconciliation tie-outs vs cartera.
    assert r.periodo_actual == "2026-06"
    assert r.base_periodo_actual_ars == Decimal("1000000.00")
    assert r.esperada_periodo_actual_ars == Decimal("100000.00")


def test_renovaciones_golden(loaded_repo):
    r = compute_renovaciones(
        loaded_repo.get_polizas(),
        loaded_repo.get_cuotas(),
        loaded_repo.get_siniestros(),
        as_of=loaded_repo.snapshot_fecha,
        thresholds=T,
        has_siniestros=loaded_repo.has_siniestros(),
    )
    assert (r.expiring_30, r.expiring_60, r.expiring_90) == (2, 3, 4)
    assert r.prima_en_juego_90_ars == Decimal("330000.00")
    assert r.comision_en_juego_90_ars == Decimal("33000.00")
    assert r.at_risk_count == 1
    assert r.at_risk_items[0].poliza_id == "POL-EXP-07"
    assert r.at_risk_prima_ars == Decimal("100000.00")
    assert r.renewal_rate == pytest.approx(0.5)
    assert r.usa_siniestros is True


def test_renovaciones_without_siniestros_degrades(tmp_path):
    from datetime import date, datetime

    from nexo_os.data.ingest import ingest
    from nexo_os.data.snapshot_repository import SnapshotRepository
    from nexo_os.tests.conftest import SYN

    repo = SnapshotRepository.open(tmp_path / "n.duckdb")
    ingest(
        SYN / "cartera_sin_siniestros.xlsx",
        cargado_por="a",
        repo=repo,
        snapshot_fecha=date(2026, 6, 30),
        now=datetime(2026, 6, 30),
    )
    try:
        r = compute_renovaciones(
            repo.get_polizas(),
            repo.get_cuotas(),
            repo.get_siniestros(),
            as_of=repo.snapshot_fecha,
            thresholds=T,
            has_siniestros=repo.has_siniestros(),
        )
        # POL-EXP-07 still at-risk via expiry + overdue, even without claim history.
        assert r.usa_siniestros is False
        assert r.at_risk_count == 1
        assert r.at_risk_items[0].poliza_id == "POL-EXP-07"
    finally:
        repo.close()


def test_comercial_golden(loaded_repo):
    r = compute_comercial(
        loaded_repo.get_leads(),
        loaded_repo.get_cotizaciones(),
        as_of=loaded_repo.snapshot_fecha,
        thresholds=T,
    )
    assert r.leads_total == 6
    assert r.open_count == 4
    assert r.quotes_total == 3
    assert r.quotes_bound == 1
    assert r.quote_to_bind == pytest.approx(1 / 3)
    assert (r.won, r.lost, r.closed) == (1, 1, 2)
    assert r.lead_to_win_closed == pytest.approx(0.5)
    assert r.pipeline_value_ars == Decimal("300000.00")
    assert r.weighted_forecast_ars == Decimal("185000.00")
    assert (r.sin_cotizacion_count, r.no_presentada_count, r.estancado_count) == (1, 1, 1)
