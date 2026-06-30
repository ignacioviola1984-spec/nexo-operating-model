"""Shared read-only dashboard views (figures from core).

Used by both the production app (nexo_os/dashboard/app.py) and the CV demo
(nexo_os/dashboard/demo.py). No auth here; callers gate access. Every figure
comes from core - never the model.
"""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from nexo_os import strings_es as S
from nexo_os.config import get_settings
from nexo_os.core.cartera import compute_cartera
from nexo_os.core.cobranza import compute_cobranza
from nexo_os.core.comercial import compute_comercial
from nexo_os.core.comisiones import compute_comisiones
from nexo_os.core.renovaciones import compute_renovaciones


def _thresholds():
    return get_settings().thresholds


def fmt_ars(value: Decimal | None) -> str:
    if value is None:
        return S.SIN_DATOS
    return "ARS " + f"{int(value):,}".replace(",", ".")


def snapshot_banner(repo) -> bool:
    snap = repo.active_snapshot()
    if snap is None:
        st.warning(S.SIN_SNAPSHOT)
        return False
    st.info(f"{S.SNAPSHOT_FECHA}: **{snap.snapshot_fecha}**  (id `{snap.snapshot_id}`)")
    return True


def resumen_view(repo) -> None:
    st.header(S.NAV_RESUMEN)
    if not snapshot_banner(repo):
        return
    t = _thresholds()
    as_of = repo.snapshot_fecha
    car = compute_cartera(
        repo.get_polizas(),
        repo.get_clientes(),
        thresholds=t,
        prev_polizas=repo.prev_polizas() or None,
        prev_clientes=repo.prev_clientes() or None,
    )
    cob = compute_cobranza(
        repo.get_cuotas(), repo.get_polizas(), repo.get_clientes(), as_of=as_of, thresholds=t
    )
    com = compute_comisiones(repo.get_comisiones(), as_of=as_of, thresholds=t)
    comm = compute_comercial(repo.get_leads(), repo.get_cotizaciones(), as_of=as_of, thresholds=t)

    c1, c2, c3 = st.columns(3)
    c1.metric("Polizas en vigor", car.polizas_en_vigor)
    c2.metric("Prima total", fmt_ars(car.prima_total))
    c3.metric("Comision esperada", fmt_ars(car.comision_esperada_total))
    c4, c5, c6 = st.columns(3)
    rate = "—" if cob.delinquency_rate is None else f"{cob.delinquency_rate:.1%}"
    c4.metric("Mora %", rate)
    c5.metric("Cobranza pendiente", fmt_ars(cob.total_overdue_ars))
    c6.metric("Comisiones por cobrar (dif.)", fmt_ars(com.total_diferencia_ars))
    c7, c8, _ = st.columns(3)
    c7.metric("Pipeline abierto", fmt_ars(comm.pipeline_value_ars))
    c8.metric("Pronostico ponderado", fmt_ars(comm.weighted_forecast_ars))
    if car.concentracion_alerta:
        st.warning(f"Concentracion alta: {car.aseguradora_dominante} = {car.share_dominante:.0%}.")


def cobranza_view(repo) -> None:
    st.header(S.NAV_COBRANZA)
    if not snapshot_banner(repo):
        return
    r = compute_cobranza(
        repo.get_cuotas(),
        repo.get_polizas(),
        repo.get_clientes(),
        as_of=repo.snapshot_fecha,
        thresholds=_thresholds(),
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Cuotas en mora", r.overdue_count)
    c2.metric("Total en mora", fmt_ars(r.total_overdue_ars))
    c3.metric(
        "DSO (dias)",
        "—" if r.dias_mora_promedio_ponderado is None else f"{r.dias_mora_promedio_ponderado:.0f}",
    )
    st.subheader("Por tramo de mora")
    st.table(
        [
            {"tramo": b, "cuotas": r.bucket_counts[b], "ARS": fmt_ars(r.bucket_ars[b])}
            for b in r.bucket_counts
        ]
    )


def renovaciones_view(repo) -> None:
    st.header(S.NAV_RENOVACIONES)
    if not snapshot_banner(repo):
        return
    r = compute_renovaciones(
        repo.get_polizas(),
        repo.get_cuotas(),
        repo.get_siniestros(),
        as_of=repo.snapshot_fecha,
        thresholds=_thresholds(),
        has_siniestros=repo.has_siniestros(),
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Vencen <=30 / 60 / 90", f"{r.expiring_30} / {r.expiring_60} / {r.expiring_90}")
    c2.metric("Comision en juego (<=90)", fmt_ars(r.comision_en_juego_90_ars))
    c3.metric("En riesgo", r.at_risk_count)
    if not r.usa_siniestros:
        st.caption("Riesgo calculado SIN historial de siniestros (no provisto).")


def comisiones_view(repo) -> None:
    st.header(S.NAV_COMISIONES)
    if not snapshot_banner(repo):
        return
    r = compute_comisiones(
        repo.get_comisiones(), as_of=repo.snapshot_fecha, thresholds=_thresholds()
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Esperada", fmt_ars(r.total_esperada_ars))
    c2.metric("Liquidada", fmt_ars(r.total_liquidada_ars))
    c3.metric("Diferencia", fmt_ars(r.total_diferencia_ars))
    st.metric("Discrepancias / vencidas", f"{r.discrepancia_count} / {r.aged_count}")


def cartera_view(repo) -> None:
    st.header(S.NAV_CARTERA)
    if not snapshot_banner(repo):
        return
    r = compute_cartera(
        repo.get_polizas(),
        repo.get_clientes(),
        thresholds=_thresholds(),
        prev_polizas=repo.prev_polizas() or None,
        prev_clientes=repo.prev_clientes() or None,
    )
    crec = S.SIN_BASE if r.crecimiento_prima is None else f"{r.crecimiento_prima:.1%}"
    st.metric("Crecimiento de prima vs snapshot anterior", crec)
    st.subheader("Mix por aseguradora")
    st.table([{"aseguradora": k, "prima": fmt_ars(v)} for k, v in r.mix_aseguradora.items()])
    st.subheader("Mix por ramo")
    st.table([{"ramo": k, "prima": fmt_ars(v)} for k, v in r.mix_ramo.items()])


def comercial_view(repo) -> None:
    st.header(S.NAV_COMERCIAL)
    if not snapshot_banner(repo):
        return
    r = compute_comercial(
        repo.get_leads(),
        repo.get_cotizaciones(),
        as_of=repo.snapshot_fecha,
        thresholds=_thresholds(),
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Leads abiertos", r.open_count)
    c2.metric("Pipeline", fmt_ars(r.pipeline_value_ars))
    c3.metric("Pronostico ponderado", fmt_ars(r.weighted_forecast_ars))
    q2b = "—" if r.quote_to_bind is None else f"{r.quote_to_bind:.0%}"
    st.metric("Conversion cotizacion->poliza", q2b)


def auditoria_view(repo) -> None:
    from nexo_os import audit

    st.header(S.NAV_AUDITORIA)
    ok, bad = audit.verify_chain(repo)
    if ok:
        st.success(S.AUDIT_OK)
    else:
        st.error(f"{S.AUDIT_ROTA} (evento #{bad})")
    events = repo.read_audit()
    st.table(
        [
            {
                "ts": str(e.ts),
                "actor": e.actor,
                "accion": e.accion,
                "entidad": f"{e.entidad_tipo or ''} {e.entidad_id or ''}".strip(),
            }
            for e in events[-200:]
        ]
    )
