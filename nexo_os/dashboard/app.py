"""Local Streamlit dashboard for Nexo v3 (Spanish UI) - the production app.

Login -> upload+validation -> executive overview -> one view per agent -> HITL
inbox -> audit view. No page is reachable without authentication. Every figure
shown comes from core (never the model); the inbox is the spine. Approving records
the decision and sends nothing.

Run: `make run`  (=> streamlit run nexo_os/dashboard/app.py)
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from nexo_os import strings_es as S
from nexo_os.auth import AuthError, authenticate, new_session
from nexo_os.config import get_settings
from nexo_os.dashboard import actions
from nexo_os.dashboard.views import auditoria_view as _auditoria_view
from nexo_os.dashboard.views import (
    cartera_view,
    cobranza_view,
    comercial_view,
    comisiones_view,
    fmt_ars,
    renovaciones_view,
    resumen_view,
)
from nexo_os.data import store as _store
from nexo_os.data.schema.models import EstadoAccion, Rol
from nexo_os.data.snapshot_repository import SnapshotRepository
from nexo_os.data.template import TEMPLATE_NAME, build_template
from nexo_os.orchestrator import run_cycle


def _settings():
    return get_settings()


def _repo() -> SnapshotRepository:
    if "repo" not in st.session_state:
        st.session_state.repo = SnapshotRepository.open(_settings().store_path)
    return st.session_state.repo


def _now() -> datetime:
    return datetime.now()


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
# Auth-bound views
# --------------------------------------------------------------------------- #
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

    # Backup of the local system of record (PII; keep off-repo - see SECURITY.md).
    st.divider()
    st.subheader("Respaldo del store local")
    last = _store.last_backup(_settings().backup_dir)
    st.caption(f"Ultimo backup: {last.name if last else 'nunca'}")
    if st.button("Crear backup ahora"):
        dest = _store.backup(_settings().store_path, _settings().backup_dir)
        st.success(f"Backup creado: {dest.name}")


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
        head = (
            f"[{a.prioridad.value.upper()}] {a.agente} · {a.tipo_accion} · "
            f"{monto} · conf {a.confianza:.0%}"
        )
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
    _auditoria_view(repo)


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
