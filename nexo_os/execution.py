"""Execution seam - DISABLED in this build (§1, §13).

No outbound execution exists: nothing is sent or written to any external system.
Approving an action records the decision; it does not act. This interface is the
explicit, clearly-marked seam for a future build; only `NoopExecutionAdapter` is
wired, and it merely records a 'would execute' note to the audit log.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from nexo_os import audit
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import Accion


class ExecutionAdapter(ABC):
    """Seam for a future outbound channel. Not wired live in this build."""

    @abstractmethod
    def execute(self, repo: NexoRepository, accion: Accion, *, now: datetime) -> str: ...


class NoopExecutionAdapter(ExecutionAdapter):
    """The only adapter. Sends nothing; records a 'would execute' audit note."""

    enabled = False

    def execute(self, repo: NexoRepository, accion: Accion, *, now: datetime) -> str:
        audit.record_event(
            repo,
            actor="execution:noop",
            accion="would_execute",
            ts=now,
            entidad_tipo="accion",
            entidad_id=accion.accion_id,
            detalle={"nota": "seam deshabilitado; no se envia nada"},
        )
        return "noop"
