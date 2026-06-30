"""Authorization-guarded dashboard actions (testable without Streamlit).

Every privileged action goes through a guard here, so a reused/forgotten UI path
can never smuggle an ungated action through. The Streamlit app calls these; the
RBAC eval (§16) targets them directly.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from nexo_os import auth, review
from nexo_os.auth import AuthError, Session
from nexo_os.data.ingest import IngestResult, ingest
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import Accion


def do_upload(
    repo: NexoRepository,
    session: Session | None,
    workbook: Path,
    *,
    snapshot_fecha: date,
    now: datetime,
) -> IngestResult:
    """Ingest a workbook. Restricted to admin (fails closed otherwise)."""
    s = auth.require_admin(session, now=now)
    return ingest(
        workbook, cargado_por=s.usuario, repo=repo, snapshot_fecha=snapshot_fecha, now=now
    )


def _require_reviewer(session: Session | None, now: datetime) -> Session:
    s = auth.require_authenticated(session, now=now)
    if not auth.can_review(s.rol):
        raise AuthError("El rol no puede operar la bandeja de aprobaciones.")
    return s


def do_approve(
    repo: NexoRepository,
    session: Session | None,
    accion_id: str,
    *,
    now: datetime,
    nota: str | None = None,
) -> Accion:
    s = _require_reviewer(session, now)
    return review.approve(repo, accion_id, by=s.usuario, now=now, nota=nota)


def do_reject(
    repo: NexoRepository,
    session: Session | None,
    accion_id: str,
    *,
    now: datetime,
    nota: str | None = None,
) -> Accion:
    s = _require_reviewer(session, now)
    return review.reject(repo, accion_id, by=s.usuario, now=now, nota=nota)


def do_edit(
    repo: NexoRepository,
    session: Session | None,
    accion_id: str,
    nuevo_mensaje: str,
    *,
    now: datetime,
    nota: str | None = None,
) -> Accion:
    s = _require_reviewer(session, now)
    return review.edit(repo, accion_id, nuevo_mensaje, by=s.usuario, now=now, nota=nota)
