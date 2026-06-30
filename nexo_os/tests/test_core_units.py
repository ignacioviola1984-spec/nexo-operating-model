"""Phase 3 unit tests: money/aging primitives + core edge cases.

Edge cases assert the fail-closed stance: missing data yields explicit
None / 'sin base', never a fabricated 0 that reads as real.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nexo_os.config import Thresholds
from nexo_os.core import money
from nexo_os.core.aging import (
    bucket_mora,
    dias_aging_comision,
    is_overdue,
    outstanding,
    periodo_end,
)
from nexo_os.core.cartera import compute_cartera
from nexo_os.core.cobranza import compute_cobranza
from nexo_os.core.comercial import compute_comercial
from nexo_os.core.comisiones import compute_comisiones
from nexo_os.data.schema.models import Cuota

T = Thresholds()


# --- money ------------------------------------------------------------------ #
def test_money_rounding_half_up():
    assert money.ars(Decimal("1.005")) == Decimal("1.01")
    assert money.ars("2.004") == Decimal("2.00")


def test_money_total_is_exact():
    assert money.total([Decimal("0.1"), Decimal("0.2")]) == Decimal("0.30")


def test_ratio_and_pct_change_guard_zero():
    assert money.ratio(Decimal("1"), Decimal("0")) is None
    assert money.pct_change(Decimal("1"), Decimal("0")) is None
    assert money.hhi([Decimal("1")], Decimal("0")) is None
    assert money.ratio(Decimal("1"), Decimal("4")) == 0.25


# --- aging ------------------------------------------------------------------ #
def _cuota(estado, venc, monto, pagado=None):
    return Cuota(
        cuota_id="x",
        poliza_id="p",
        nro_cuota=1,
        fecha_vencimiento=venc,
        monto_ars=Decimal(monto),
        estado=estado,
        monto_pagado_ars=pagado,
    )


def test_outstanding_by_state():
    assert outstanding(_cuota("pagada", date(2026, 1, 1), "100")) == Decimal("0")
    assert outstanding(_cuota("parcial", date(2026, 1, 1), "100", Decimal("30"))) == Decimal("70")
    assert outstanding(_cuota("pendiente", date(2026, 1, 1), "100")) == Decimal("100")


def test_is_overdue_respects_due_date_and_state():
    as_of = date(2026, 6, 30)
    assert is_overdue(_cuota("vencida", date(2026, 6, 1), "100"), as_of) is True
    assert is_overdue(_cuota("pendiente", date(2026, 7, 1), "100"), as_of) is False  # future
    assert is_overdue(_cuota("pagada", date(2026, 1, 1), "100"), as_of) is False


def test_bucket_boundaries():
    b = (30, 60, 90)
    assert bucket_mora(0, b).value == "0"
    assert bucket_mora(30, b).value == "1-30"
    assert bucket_mora(31, b).value == "31-60"
    assert bucket_mora(90, b).value == "61-90"
    assert bucket_mora(91, b).value == "90+"


def test_periodo_end_and_commission_aging():
    assert periodo_end("2026-02") == date(2026, 2, 28)
    # 2026-03 -> end 03-31 + 30d offset = 04-30; to 06-30 = 61 days.
    assert dias_aging_comision("2026-03", date(2026, 6, 30), 30) == 61
    # current period not yet due -> 0.
    assert dias_aging_comision("2026-06", date(2026, 6, 30), 30) == 0


# --- core edge cases (fail-closed) ------------------------------------------ #
def test_cartera_empty_no_alert_no_division():
    r = compute_cartera([], [], thresholds=T)
    assert r.polizas_en_vigor == 0
    assert r.prima_total == Decimal("0.00")
    assert r.hhi_aseguradora is None
    assert r.concentracion_alerta is False
    assert r.sin_base_comparacion is True


def test_cobranza_empty_rate_is_none_not_zero():
    r = compute_cobranza([], [], [], as_of=date(2026, 6, 30), thresholds=T)
    assert r.overdue_count == 0
    assert r.total_overdue_ars == Decimal("0.00")
    assert r.delinquency_rate is None  # no receivable -> sin datos, not a fake 0
    assert r.dias_mora_promedio_ponderado is None


def test_comisiones_all_settled_no_discrepancy():
    from nexo_os.data.schema.models import Comision

    c = Comision(
        comision_id="c",
        poliza_id="p",
        aseguradora_id="a",
        periodo="2026-06",
        base_comisionable_ars=Decimal("1000"),
        comision_pct=Decimal("0.10"),
        comision_esperada_ars=Decimal("100"),
        comision_liquidada_ars=Decimal("100"),
        estado="liquidada",
    )
    r = compute_comisiones([c], as_of=date(2026, 6, 30), thresholds=T)
    assert r.total_diferencia_ars == Decimal("0.00")
    assert r.discrepancia_count == 0
    assert r.aged_count == 0


def test_comercial_empty_conversions_none():
    r = compute_comercial([], [], as_of=date(2026, 6, 30), thresholds=T)
    assert r.leads_total == 0
    assert r.quote_to_bind is None
    assert r.lead_to_win_total is None
    assert r.pipeline_value_ars == Decimal("0.00")
