"""The single data-access boundary for Nexo v3.

Agents and core NEVER read a file or run a query directly - everything goes
through a `NexoRepository`. Return types are explicit and typed (no `Any`, no
untyped dicts crossing the boundary). The one production implementation is
`SnapshotRepository` (DuckDB); the abstraction exists for testability and future
option value, NOT as a reason to add services. No cloud implementation exists.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from nexo_os.data.schema.models import (
    Accion,
    AgentRun,
    Aseguradora,
    AuditEvent,
    Cliente,
    Comision,
    Cotizacion,
    Cuota,
    DataSnapshot,
    EstadoAccion,
    Lead,
    Poliza,
    Productor,
    Siniestro,
    Usuario,
)


class NexoRepository(ABC):
    """Typed reads of the active snapshot + reads/writes of the system tables.

    The contract: agent code is identical regardless of which snapshot is active
    or how it arrived. The active snapshot defines the run's as-of date
    (`snapshot_fecha`); there is no scattered now().
    """

    # --- snapshot context -------------------------------------------------- #
    @property
    @abstractmethod
    def snapshot_fecha(self) -> date:
        """The as-of date for this run (the active snapshot's date)."""

    @abstractmethod
    def active_snapshot(self) -> DataSnapshot | None:
        """The currently-active snapshot, or None if nothing is loaded yet."""

    @abstractmethod
    def get_previous_snapshot(self) -> DataSnapshot | None:
        """Most recent ARCHIVED snapshot, or None on the very first upload.

        Growth/trend metrics use this; when None they must return an explicit
        'sin base de comparacion' result, never a fabricated delta.
        """

    # --- operational reads (active snapshot only) -------------------------- #
    @abstractmethod
    def get_clientes(self) -> list[Cliente]: ...

    @abstractmethod
    def get_polizas(self) -> list[Poliza]: ...

    @abstractmethod
    def get_cuotas(self) -> list[Cuota]: ...

    @abstractmethod
    def get_comisiones(self) -> list[Comision]: ...

    @abstractmethod
    def get_leads(self) -> list[Lead]: ...

    @abstractmethod
    def get_cotizaciones(self) -> list[Cotizacion]: ...

    @abstractmethod
    def get_siniestros(self) -> list[Siniestro]:
        """Optional sheet: returns [] when the broker did not provide it."""

    @abstractmethod
    def get_aseguradoras(self) -> list[Aseguradora]: ...

    @abstractmethod
    def get_productores(self) -> list[Productor]: ...

    @abstractmethod
    def has_siniestros(self) -> bool:
        """Whether the active snapshot actually carries siniestros data."""

    # --- system tables: snapshots ----------------------------------------- #
    @abstractmethod
    def list_snapshots(self) -> list[DataSnapshot]: ...

    # --- system tables: HITL inbox (acciones) ------------------------------ #
    @abstractmethod
    def add_accion(self, accion: Accion) -> None: ...

    @abstractmethod
    def list_acciones(
        self,
        *,
        estado: EstadoAccion | None = None,
        run_id: str | None = None,
    ) -> list[Accion]: ...

    @abstractmethod
    def get_accion(self, accion_id: str) -> Accion | None: ...

    @abstractmethod
    def resolve_accion(self, accion: Accion) -> None:
        """Persist a resolved (approved/edited/rejected) action row."""

    # --- system tables: agent runs ---------------------------------------- #
    @abstractmethod
    def add_run(self, run: AgentRun) -> None: ...

    @abstractmethod
    def update_run(self, run: AgentRun) -> None: ...

    # --- system tables: audit log (append-only, hash-chained) -------------- #
    @abstractmethod
    def append_audit(self, event: AuditEvent) -> None:
        """Append one event. MUST NOT update/delete prior rows."""

    @abstractmethod
    def last_audit(self) -> AuditEvent | None:
        """The most recent audit event (for chaining the next one)."""

    @abstractmethod
    def read_audit(self) -> list[AuditEvent]:
        """All audit events in chain order."""

    @abstractmethod
    def audit_count(self) -> int:
        """Number of audit events (for chain-position ids)."""

    # --- system tables: users (auth/RBAC) --------------------------------- #
    @abstractmethod
    def add_usuario(self, usuario: Usuario) -> None: ...

    @abstractmethod
    def get_usuario(self, usuario: str) -> Usuario | None: ...

    @abstractmethod
    def list_usuarios(self) -> list[Usuario]: ...
