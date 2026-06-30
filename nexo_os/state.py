"""NexoContext - the shared, auditable state for one orchestrator run.

Holds the run's as-of date, each agent's results and proposed actions, cross-agent
shared figures, and consolidated escalations. Every action proposed and every
escalation is recorded to the hash-chained audit log via the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from nexo_os import audit
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import Accion


@dataclass
class Escalation:
    severidad: str  # alta | media | baja
    fuente: str
    mensaje: str


class NexoContext:
    def __init__(
        self,
        repo: NexoRepository,
        *,
        run_id: str,
        snapshot_id: str,
        snapshot_fecha: date,
        now: datetime,
    ):
        self.repo = repo
        self.run_id = run_id
        self.snapshot_id = snapshot_id
        self.snapshot_fecha = snapshot_fecha
        self.now = now
        self.results: dict[str, object] = {}
        self.acciones: list[Accion] = []
        self.shared: dict[str, object] = {}
        self.escalaciones: list[Escalation] = []

    # --- agent results ----------------------------------------------------- #
    def put_result(self, agente: str, result: object) -> None:
        self.results[agente] = result

    def get_result(self, agente: str) -> object | None:
        return self.results.get(agente)

    # --- cross-agent shared figures (computed once, reused) ---------------- #
    def set_shared(self, key: str, value: object) -> None:
        self.shared[key] = value

    def get_shared(self, key: str, default: object = None) -> object:
        return self.shared.get(key, default)

    # --- proposed actions (maker side) ------------------------------------- #
    def add_accion(self, accion: Accion) -> None:
        """Persist a proposed action and audit the proposal (identifiers only)."""
        self.acciones.append(accion)
        self.repo.add_accion(accion)
        audit.record_event(
            self.repo,
            actor=f"agente:{accion.agente}",
            accion="propose",
            ts=self.now,
            entidad_tipo=accion.entidad_tipo,
            entidad_id=accion.entidad_id,
            detalle={
                "accion_id": accion.accion_id,
                "tipo_accion": accion.tipo_accion,
                "prioridad": accion.prioridad.value,
                "confianza": accion.confianza,
                "run_id": self.run_id,
            },
        )

    # --- escalations (reliability/reconciliation) -------------------------- #
    def escalate(self, severidad: str, fuente: str, mensaje: str) -> None:
        esc = Escalation(severidad=severidad, fuente=fuente, mensaje=mensaje)
        self.escalaciones.append(esc)
        audit.record_event(
            self.repo,
            actor="reliability",
            accion="escalation",
            ts=self.now,
            detalle={"severidad": severidad, "fuente": fuente},
        )
