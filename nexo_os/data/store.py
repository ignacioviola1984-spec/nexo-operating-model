"""Local DuckDB store: connection, schema bootstrap, and backup/restore.

The store is the system of record (snapshots, the HITL inbox, agent runs, the
hash-chained audit log). It lives entirely on the local machine; there is no
cloud backup, so backup/restore here is the only safety net for the
approval/audit history. See SECURITY.md.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import duckdb

SCHEMA_SQL = Path(__file__).resolve().parent / "schema" / "schema.sql"


def connect(store_path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (creating parent dirs as needed) and ensure the schema exists."""
    store_path = Path(store_path)
    if not read_only:
        store_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(store_path), read_only=read_only)
    if not read_only:
        init_schema(con)
    return con


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Execute the canonical DDL (idempotent: every statement is IF NOT EXISTS)."""
    con.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


def backup(store_path: Path, backup_dir: Path, *, stamp: str | None = None) -> Path:
    """Checkpoint and copy the store to a dated file under backup_dir.

    `stamp` lets callers pass a deterministic timestamp (tests/CI); otherwise a
    wall-clock UTC stamp is used.
    """
    store_path = Path(store_path)
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not store_path.exists():
        raise FileNotFoundError(f"No store to back up at {store_path}")

    # Flush WAL into the main file so the copy is a consistent snapshot.
    con = duckdb.connect(str(store_path))
    try:
        con.execute("CHECKPOINT")
    finally:
        con.close()

    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"nexo-{stamp}.duckdb"
    shutil.copy2(store_path, dest)
    return dest


def restore(backup_file: Path, store_path: Path) -> Path:
    """Restore the store from a backup file (overwrites the current store)."""
    backup_file = Path(backup_file)
    store_path = Path(store_path)
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup not found: {backup_file}")
    store_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_file, store_path)
    return store_path


def last_backup(backup_dir: Path) -> Path | None:
    """Most recent backup file (by name, which is timestamp-sortable), or None."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return None
    backups = sorted(backup_dir.glob("nexo-*.duckdb"))
    return backups[-1] if backups else None
