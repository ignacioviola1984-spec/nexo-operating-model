"""Maker-checker (§9): the broker resolves each proposed action.

Agent = maker (proposes), broker = checker (approves / edits / rejects). An action
is not 'done' until a human resolves it; every decision is recorded with user +
timestamp on the acciones row AND to the hash-chained audit log. Nothing outbound
executes here - approval records the decision, it sends nothing.
"""

from __future__ import annotations

from datetime import datetime

from nexo_os import audit
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import Accion, EstadoAccion


class ReviewError(RuntimeError):
    """Raised on an invalid review transition (missing or already-resolved)."""


def _load_pending(repo: NexoRepository, accion_id: str) -> Accion:
    accion = repo.get_accion(accion_id)
    if accion is None:
        raise ReviewError(f"Accion no encontrada: {accion_id}")
    if accion.estado != EstadoAccion.propuesta:
        raise ReviewError(f"Accion {accion_id} ya resuelta (estado={accion.estado.value}).")
    return accion


def _resolve(
    repo: NexoRepository,
    accion: Accion,
    *,
    estado: EstadoAccion,
    by: str,
    now: datetime,
    nota: str | None,
    accion_audit: str,
) -> Accion:
    accion.estado = estado
    accion.resuelta_en = now
    accion.resuelta_por = by
    accion.nota_revisor = nota
    repo.resolve_accion(accion)
    audit.record_event(
        repo,
        actor=by,
        accion=accion_audit,
        ts=now,
        entidad_tipo="accion",
        entidad_id=accion.accion_id,
        detalle={"estado": estado.value, "tiene_nota": bool(nota)},
    )
    return accion


def approve(
    repo: NexoRepository, accion_id: str, *, by: str, now: datetime, nota: str | None = None
) -> Accion:
    accion = _load_pending(repo, accion_id)
    return _resolve(
        repo,
        accion,
        estado=EstadoAccion.aprobada,
        by=by,
        now=now,
        nota=nota,
        accion_audit="approve",
    )


def reject(
    repo: NexoRepository, accion_id: str, *, by: str, now: datetime, nota: str | None = None
) -> Accion:
    accion = _load_pending(repo, accion_id)
    return _resolve(
        repo,
        accion,
        estado=EstadoAccion.rechazada,
        by=by,
        now=now,
        nota=nota,
        accion_audit="reject",
    )


def edit(
    repo: NexoRepository,
    accion_id: str,
    nuevo_mensaje: str,
    *,
    by: str,
    now: datetime,
    nota: str | None = None,
) -> Accion:
    """Edit the Spanish message and approve it (estado=editada)."""
    accion = _load_pending(repo, accion_id)
    accion.mensaje_es = nuevo_mensaje
    return _resolve(
        repo, accion, estado=EstadoAccion.editada, by=by, now=now, nota=nota, accion_audit="edit"
    )
