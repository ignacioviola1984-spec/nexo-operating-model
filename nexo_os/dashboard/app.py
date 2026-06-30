"""Local Streamlit dashboard for Nexo v3 (Spanish UI).

Login -> upload+validation -> executive overview -> one view per agent -> HITL
inbox -> audit view. No page is reachable without authentication. Every figure
shown comes from core (never the model); the inbox is the spine. Approving records
the decision and sends nothing.

Run: `make run`  (=> streamlit run nexo_os/dashboard/app.py)
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

from nexo_os import strings_es as S
from nexo_os.auth import AuthError, authenticate, new_session
from nexo_os.config import get_settings
from nexo_os.core.cartera import compute_cartera
from nexo_os.core.cobranza import compute_cobranza
from nexo_os.core.comercial import compute_comercial
from nexo_os.core.comisiones import compute_comisiones
from nexo_os.core.renovaciones import compute_renovaciones
from nexo_os.dashboard import actions
from nexo_os.data.schema.models import EstadoAccion, Rol
from nexo_os.data.snapshot_repository import SnapshotRepository
from nexo_os.data.template import TEMPLATE_NAME, build_template
from nexo_os.orchestrator import run_cycle


# --------------------------------------------------------------------------- #
# Infra
# --------------------------------------------------------------------------- #
def _settings():
    return get_settings()


def _repo() -> SnapshotRepository:
    if "repo" not in st.session_state:
        st.session_state.repo = SnapshotRepository.open(_settings().store_path)
    return st.session_state.repo


def _now() -> datetime:
    return datetime.now()


def fmt_ars(value: Decimal | None) -> str:
    if value is None:
        return S.SIN_DATOS
    return "ARS " + f"{int(value):,}".replace(",", ".")


def _thresholds():
    return _settings().thresholds


def _has_snapshot(repo) -> bool:
    return repo.active_snapshot() is not None


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def login_view() -> None:
    st.title(S.APP_TITLE)
    st.caption(S.APP_TAGLINE)
    st.subheader(S.LOGIN_TITLE)
    with st.form("login"):
        usuario = st.text_input(S.LOGIN_USER)
        clave = st.text_input(S.LOGIN_PASSWORD, type="password")
        if st.form_submit_button(S.LOGIN_BUTTON):
            try:
                user = authenticate(_repo(), usuario, clave, now=_now())
            except AuthError:
                st.error(S.LOGIN_ERROR)
                return
            st.session_state.session = new_session(
                user, now=_now(), ttl_minutes=_settings().session_ttl_minutes
            )
            st.session_state.nombre = user.nombre
            st.rerun()


def _session():
    s = st.session_state.get("session")
    if s is not None and not s.is_valid(_now()):
        st.session_state.pop("session", None)
        return None
    return s


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def _snapshot_banner(repo) -> bool:
    snap = repo.active_snapshot()
    if snap is None:
        st.warning(S.SIN_SNAPSHOT)
        return False
    st.info(f"{S.SNAPSHOT_FECHA}: **{snap.snapshot_fecha}**  (id `{snap.snapshot_id}`)")
    return True


def resumen_view(repo) -> None:
    st.header(S.NAV_RESUMEN)
    if not _snapshot_banner(repo):
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
    if not _snapshot_banner(repo):
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
    if not _snapshot_banner(repo):
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
    if not _snapshot_banner(repo):
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
    if not _snapshot_banner(repo):
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
    if not _snapshot_banner(repo):
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


def carga_view(repo, session) -> None:
    st.header(S.NAV_CARGA)
    if session.rol != Rol.admin:
        st.error(S.UPLOAD_SOLO_ADMIN)
        return
    tpl_path = Path(tempfile.gettempdir()) / TEMPLATE_NAME
    build_template(tpl_path)
    st.download_button(S.UPLOAD_TEMPLATE, tpl_path.read_bytes(), file_name=TEMPLATE_NAME)
    st.caption(S.UPLOAD_HELP)
    fecha = st.date_input("Fecha as-of del snapshot", value=date.today())
    uploaded = st.file_uploader("Workbook (.xlsx)", type=["xlsx"])
    if uploaded is not None and st.button("Validar y cargar"):
        tmp = Path(tempfile.gettempdir()) / uploaded.name
        tmp.write_bytes(uploaded.getbuffer())
        result = actions.do_upload(repo, session, tmp, snapshot_fecha=fecha, now=_now())
        if result.ok:
            st.success(S.UPLOAD_OK)
        else:
            st.error(S.UPLOAD_RECHAZADO)
        st.code(result.report.render_es(), language="text")


def bandeja_view(repo, session) -> None:
    st.header(S.NAV_BANDEJA)
    st.caption(S.NO_ENVIA)
    if _has_snapshot(repo) and st.button(S.CORRER_CICLO):
        run_cycle(repo, now=_now())
        st.rerun()
    pendientes = repo.list_acciones(estado=EstadoAccion.propuesta)
    if not pendientes:
        st.info(S.INBOX_VACIA)
        return
    order = {"alta": 0, "media": 1, "baja": 2}
    pendientes.sort(key=lambda a: (order.get(a.prioridad.value, 9), -a.confianza))
    for a in pendientes:
        monto = fmt_ars(a.monto_en_juego_ars) if a.monto_en_juego_ars is not None else "—"
        head = f"[{a.prioridad.value.upper()}] {a.agente} · {a.tipo_accion} · {monto} · conf {a.confianza:.0%}"
        with st.expander(head, expanded=(a.prioridad.value == "alta")):
            st.caption(f"{a.entidad_tipo} {a.entidad_id}")
            st.json(a.rationale_json)
            nuevo = st.text_area(S.MENSAJE_PROPUESTO, a.mensaje_es, key=f"m_{a.accion_id}")
            nota = st.text_input(S.NOTA_REVISOR, key=f"n_{a.accion_id}")
            b1, b2, b3 = st.columns(3)
            if b1.button(S.BTN_APROBAR, key=f"ap_{a.accion_id}"):
                actions.do_approve(repo, session, a.accion_id, now=_now(), nota=nota)
                st.rerun()
            if b2.button(S.BTN_EDITAR, key=f"ed_{a.accion_id}"):
                actions.do_edit(repo, session, a.accion_id, nuevo, now=_now(), nota=nota)
                st.rerun()
            if b3.button(S.BTN_RECHAZAR, key=f"re_{a.accion_id}"):
                actions.do_reject(repo, session, a.accion_id, now=_now(), nota=nota)
                st.rerun()


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


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title=S.APP_TITLE, layout="wide")
    session = _session()
    if session is None:
        login_view()
        return

    repo = _repo()
    with st.sidebar:
        st.write(f"**{st.session_state.get('nombre', session.usuario)}** ({session.rol.value})")
        if st.button(S.LOGOUT):
            st.session_state.pop("session", None)
            st.rerun()
        views = [
            S.NAV_RESUMEN,
            S.NAV_COBRANZA,
            S.NAV_RENOVACIONES,
            S.NAV_COMISIONES,
            S.NAV_CARTERA,
            S.NAV_COMERCIAL,
            S.NAV_BANDEJA,
            S.NAV_AUDITORIA,
        ]
        if session.rol == Rol.admin:
            views.insert(6, S.NAV_CARGA)
        choice = st.radio("Vista", views)

    if choice == S.NAV_RESUMEN:
        resumen_view(repo)
    elif choice == S.NAV_COBRANZA:
        cobranza_view(repo)
    elif choice == S.NAV_RENOVACIONES:
        renovaciones_view(repo)
    elif choice == S.NAV_COMISIONES:
        comisiones_view(repo)
    elif choice == S.NAV_CARTERA:
        cartera_view(repo)
    elif choice == S.NAV_COMERCIAL:
        comercial_view(repo)
    elif choice == S.NAV_CARGA:
        carga_view(repo, session)
    elif choice == S.NAV_BANDEJA:
        bandeja_view(repo, session)
    elif choice == S.NAV_AUDITORIA:
        auditoria_view(repo)


main()
