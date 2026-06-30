"""Tamper-evident, append-only audit log (§9).

Each event's hash chains over the prior event's hash, so any later edit/delete is
*detectable* (tamper-evident, not access control). Written only through this
writer + the repository's append-only path; application code never updates or
deletes prior rows. `detalle_json` carries IDENTIFIERS ONLY - never full PII.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import AuditEvent


def _canonical(
    evento_id: str,
    ts: datetime,
    actor: str,
    accion: str,
    entidad_tipo: str | None,
    entidad_id: str | None,
    detalle_json: str,
) -> str:
    return json.dumps(
        {
            "evento_id": evento_id,
            "ts": ts.isoformat(),
            "actor": actor,
            "accion": accion,
            "entidad_tipo": entidad_tipo,
            "entidad_id": entidad_id,
            "detalle_json": detalle_json,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def _hash(prev_hash: str | None, canonical: str) -> str:
    return hashlib.sha256(((prev_hash or "") + canonical).encode("utf-8")).hexdigest()


def record_event(
    repo: NexoRepository,
    *,
    actor: str,
    accion: str,
    ts: datetime,
    entidad_tipo: str | None = None,
    entidad_id: str | None = None,
    detalle: dict | None = None,
) -> AuditEvent:
    """Append one hash-chained audit event. `detalle` must contain identifiers
    only (no names/documents/emails/phones)."""
    n = repo.audit_count()
    evento_id = f"EVT-{n + 1:08d}"
    detalle_json = json.dumps(detalle or {}, sort_keys=True, ensure_ascii=False)
    last = repo.last_audit()
    prev_hash = last.hash if last else None
    canonical = _canonical(evento_id, ts, actor, accion, entidad_tipo, entidad_id, detalle_json)
    event = AuditEvent(
        evento_id=evento_id,
        ts=ts,
        actor=actor,
        accion=accion,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        detalle_json=detalle_json,
        prev_hash=prev_hash,
        hash=_hash(prev_hash, canonical),
    )
    repo.append_audit(event)
    return event


def verify_chain(repo: NexoRepository) -> tuple[bool, int | None]:
    """Recompute the chain. Returns (ok, first_bad_index). ok=True if intact."""
    prev_hash: str | None = None
    for idx, ev in enumerate(repo.read_audit()):
        canonical = _canonical(
            ev.evento_id,
            ev.ts,
            ev.actor,
            ev.accion,
            ev.entidad_tipo,
            ev.entidad_id,
            ev.detalle_json,
        )
        expected = _hash(prev_hash, canonical)
        if ev.prev_hash != prev_hash or ev.hash != expected:
            return False, idx
        prev_hash = ev.hash
    return True, None
