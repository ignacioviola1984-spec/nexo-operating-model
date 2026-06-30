"""Nexo v3 - public CV / portfolio demo (Streamlit).

A self-contained, NO-LOGIN showcase of the Nexo project for a CV/portfolio. It
loads 100% synthetic data (visibly fake PII), runs one full agent cycle, and
presents the same core-computed views as the production app plus a project
write-up. Safe to share: no real client data, no secrets, no outbound calls
(prose uses deterministic templates unless NEXO_USE_LLM=1).

Run:  streamlit run nexo_os/dashboard/demo.py      (or: make demo)
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from nexo_os import __version__
from nexo_os.dashboard.views import (
    auditoria_view,
    cartera_view,
    cobranza_view,
    comercial_view,
    comisiones_view,
    fmt_ars,
    renovaciones_view,
    resumen_view,
)
from nexo_os.data.ingest import ingest
from nexo_os.data.snapshot_repository import SnapshotRepository
from nexo_os.orchestrator import run_cycle

# --------------------------------------------------------------------------- #
# EDIT ME - your CV header. These are placeholders; fill in your real details.
# (Left as placeholders on purpose - not invented.)
# --------------------------------------------------------------------------- #
ABOUT = {
    "nombre": "Ignacio Viola",
    "rol": "[Tu rol / titulo profesional]",
    "bio": (
        "[Editar: 2-3 lineas sobre vos. Ej.: ingeniero de software enfocado en "
        "sistemas de datos confiables y aplicaciones de IA con humano en el ciclo.]"
    ),
    "email": "ignacioviola1984@gmail.com",
    "github": "https://github.com/[tu-usuario]",
    "linkedin": "https://www.linkedin.com/in/[tu-perfil]",
}

SYN = Path(__file__).resolve().parent.parent / "data" / "synthetic"
AS_OF = date(2026, 6, 30)
AS_OF_PRIOR = date(2026, 5, 31)
NOW = datetime(2026, 6, 30, 12, 0, 0)


@st.cache_resource(show_spinner="Cargando datos sinteticos y corriendo el ciclo...")
def _demo_repo_path() -> str:
    """Build a one-off demo store: ingest prior+current synthetic, run a cycle."""
    d = Path(tempfile.mkdtemp(prefix="nexo-demo-"))
    store = d / "demo.duckdb"
    repo = SnapshotRepository.open(store)
    ingest(
        SYN / "cartera_anterior.xlsx",
        cargado_por="demo",
        repo=repo,
        snapshot_fecha=AS_OF_PRIOR,
        now=datetime(2026, 5, 31, 9, 0, 0),
    )
    ingest(
        SYN / "cartera_actual.xlsx", cargado_por="demo", repo=repo, snapshot_fecha=AS_OF, now=NOW
    )
    run_cycle(repo, now=NOW, run_id="DEMO")
    repo.close()
    return str(store)


def _repo() -> SnapshotRepository:
    return SnapshotRepository.open(Path(_demo_repo_path()))


# --------------------------------------------------------------------------- #
# Views specific to the demo
# --------------------------------------------------------------------------- #
def proyecto_view() -> None:
    st.header("Nexo - Modelo Operativo v3")
    st.caption(f"Demo de portfolio · datos 100% sinteticos · v{__version__}")
    st.markdown("""
**Que es.** Un sistema operativo local para una correduria de seguros (AR).
Ingiere la cartera desde un Excel, corre **cinco agentes** que **proponen**
acciones (cobranza, renovaciones, comisiones, cartera, pipeline comercial), y un
humano **aprueba** cada una. Corre 100% local: sin nube, sin base hosteada.

**Los tres no-negociables**
- **Todo numero se calcula en codigo** (Decimal, trazable). El modelo nunca
  produce ni redondea una cifra: solo redacta prosa, con un *guard de grounding*
  que rechaza cualquier numero que no este en el rationale.
- **Humano en el ciclo** en cada accion; decisiones en un audit log **encadenado
  por hash** (a prueba de manipulacion).
- **Falla cerrado**: un Excel invalido se rechaza entero; nunca se ingiere a medias.
        """)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Agentes", "5")
    c2.metric("Tests", "87")
    c3.metric("Evals (gate)", "9/9")
    c4.metric("Dependencias cloud", "0")
    st.markdown("""
**Stack.** Python · pydantic (modelo tipado) · DuckDB (store local de snapshots) ·
openpyxl (ingesta Excel) · Streamlit (tablero) · Anthropic Claude (prosa, opt-in) ·
bcrypt (auth) · pytest + ruff/black.

**Arquitectura.** Ingesta fail-closed -> snapshot inmutable -> core deterministico
-> agentes (compute/propose/narrate) -> reconciliaciones entre agentes -> bandeja
HITL -> auditoria. Una sola frontera de datos (repository); el modelo solo redacta.
        """)
    st.info(
        "Esta demo carga datos ficticios y corrio un ciclo completo de agentes. "
        "Navega las vistas a la izquierda: cada cifra proviene del core, no del modelo."
    )


def about_view() -> None:
    st.header(ABOUT["nombre"])
    st.subheader(ABOUT["rol"])
    st.write(ABOUT["bio"])
    cols = st.columns(3)
    cols[0].markdown(f"✉️ [{ABOUT['email']}](mailto:{ABOUT['email']})")
    cols[1].markdown(f"💻 [GitHub]({ABOUT['github']})")
    cols[2].markdown(f"🔗 [LinkedIn]({ABOUT['linkedin']})")
    st.caption("Editá nexo_os/dashboard/demo.py (ABOUT) para completar tus datos.")


def bandeja_demo_view(repo) -> None:
    st.header("Bandeja de aprobaciones (demo, solo lectura)")
    st.caption(
        "En produccion el humano aprueba/edita/rechaza cada accion y queda auditado. "
        "Aca se muestran las propuestas generadas por el ciclo."
    )
    from nexo_os.data.schema.models import EstadoAccion

    pendientes = repo.list_acciones(estado=EstadoAccion.propuesta)
    order = {"alta": 0, "media": 1, "baja": 2}
    pendientes.sort(key=lambda a: (order.get(a.prioridad.value, 9), -a.confianza))
    st.caption(f"{len(pendientes)} acciones propuestas")
    for a in pendientes:
        monto = fmt_ars(a.monto_en_juego_ars) if a.monto_en_juego_ars is not None else "—"
        head = (
            f"[{a.prioridad.value.upper()}] {a.agente} · {a.tipo_accion} · "
            f"{monto} · conf {a.confianza:.0%}"
        )
        with st.expander(head):
            st.caption(f"{a.entidad_tipo} {a.entidad_id}")
            st.write(a.mensaje_es)
            st.json(a.rationale_json)


def main() -> None:
    st.set_page_config(page_title="Nexo v3 - Demo", layout="wide")
    repo = _repo()
    with st.sidebar:
        st.title("Nexo v3 · Demo")
        choice = st.radio(
            "Seccion",
            [
                "Proyecto",
                "Sobre mi",
                "Resumen ejecutivo",
                "Cobranza",
                "Renovaciones",
                "Comisiones",
                "Cartera",
                "Pipeline comercial",
                "Bandeja",
                "Auditoria",
            ],
        )
        st.divider()
        st.caption("Datos 100% sinteticos. Sin PII real. Sin llamadas externas.")

    if choice == "Proyecto":
        proyecto_view()
    elif choice == "Sobre mi":
        about_view()
    elif choice == "Resumen ejecutivo":
        resumen_view(repo)
    elif choice == "Cobranza":
        cobranza_view(repo)
    elif choice == "Renovaciones":
        renovaciones_view(repo)
    elif choice == "Comisiones":
        comisiones_view(repo)
    elif choice == "Cartera":
        cartera_view(repo)
    elif choice == "Pipeline comercial":
        comercial_view(repo)
    elif choice == "Bandeja":
        bandeja_demo_view(repo)
    elif choice == "Auditoria":
        auditoria_view(repo)


main()
