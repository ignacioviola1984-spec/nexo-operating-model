"""SnapshotRepository - the one production NexoRepository (DuckDB).

Reads the active snapshot and the system tables from the local DuckDB store.
Operational reads are scoped to the single `activo` snapshot; the as-of date is
that snapshot's `snapshot_fecha` (or a configured override). Aging and
diferencia_ars are computed downstream (core) relative to this date.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path

import duckdb

from nexo_os.data import store as store_mod
from nexo_os.data.repository import NexoRepository
from nexo_os.data.schema.models import (
    OPERATIONAL_TABLES,
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
    EstadoSnapshot,
    Lead,
    Poliza,
    Productor,
    Siniestro,
    _Row,
)


def _to_db(value: object) -> object:
    """Coerce a domain value to something DuckDB can bind."""
    if isinstance(value, Enum):
        return value.value
    return value


def _model_columns(model_cls: type[_Row]) -> list[str]:
    return list(model_cls.model_fields.keys())


class SnapshotRepository(NexoRepository):
    def __init__(self, con: duckdb.DuckDBPyConnection, *, fecha_override: date | None = None):
        self._con = con
        self._fecha_override = fecha_override
        self._active_cache: DataSnapshot | None = None
        self._active_resolved = False

    # --- construction ------------------------------------------------------ #
    @classmethod
    def open(cls, store_path: Path, *, fecha_override: date | None = None) -> SnapshotRepository:
        con = store_mod.connect(Path(store_path))
        return cls(con, fecha_override=fecha_override)

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        return self._con

    def close(self) -> None:
        self._con.close()

    # --- snapshot context -------------------------------------------------- #
    def active_snapshot(self) -> DataSnapshot | None:
        if not self._active_resolved:
            rows = self._select(
                DataSnapshot,
                "data_snapshots",
                where="estado = ?",
                params=[EstadoSnapshot.activo.value],
            )
            self._active_cache = rows[0] if rows else None
            self._active_resolved = True
        return self._active_cache

    def _active_id(self) -> str:
        snap = self.active_snapshot()
        if snap is None:
            raise RuntimeError("No hay snapshot activo. Carga un workbook valido antes de operar.")
        return snap.snapshot_id

    @property
    def snapshot_fecha(self) -> date:
        if self._fecha_override is not None:
            return self._fecha_override
        snap = self.active_snapshot()
        if snap is None:
            raise RuntimeError("No hay snapshot activo: no se puede determinar la fecha as-of.")
        return snap.snapshot_fecha

    def get_previous_snapshot(self) -> DataSnapshot | None:
        rows = self._select(
            DataSnapshot,
            "data_snapshots",
            where="estado = ?",
            params=[EstadoSnapshot.archivado.value],
            order_by="snapshot_fecha DESC, cargado_en DESC",
        )
        return rows[0] if rows else None

    def list_snapshots(self) -> list[DataSnapshot]:
        return self._select(DataSnapshot, "data_snapshots", order_by="cargado_en DESC")

    # --- operational reads (active snapshot) ------------------------------- #
    def _read_operational(self, model_cls: type[_Row], table: str) -> list[_Row]:
        return self._select(model_cls, table, where="snapshot_id = ?", params=[self._active_id()])

    def get_clientes(self) -> list[Cliente]:
        return self._read_operational(Cliente, "clientes")  # type: ignore[return-value]

    def get_polizas(self) -> list[Poliza]:
        return self._read_operational(Poliza, "polizas")  # type: ignore[return-value]

    def get_cuotas(self) -> list[Cuota]:
        return self._read_operational(Cuota, "cuotas")  # type: ignore[return-value]

    def get_comisiones(self) -> list[Comision]:
        return self._read_operational(Comision, "comisiones")  # type: ignore[return-value]

    def get_leads(self) -> list[Lead]:
        return self._read_operational(Lead, "leads")  # type: ignore[return-value]

    def get_cotizaciones(self) -> list[Cotizacion]:
        return self._read_operational(Cotizacion, "cotizaciones")  # type: ignore[return-value]

    def get_siniestros(self) -> list[Siniestro]:
        return self._read_operational(Siniestro, "siniestros")  # type: ignore[return-value]

    def get_aseguradoras(self) -> list[Aseguradora]:
        return self._read_operational(Aseguradora, "aseguradoras")  # type: ignore[return-value]

    def get_productores(self) -> list[Productor]:
        return self._read_operational(Productor, "productores")  # type: ignore[return-value]

    def prev_polizas(self) -> list[Poliza]:
        """Polizas of the most recent ARCHIVED snapshot (for growth), or []."""
        snap = self.get_previous_snapshot()
        if snap is None:
            return []
        return self._select(Poliza, "polizas", where="snapshot_id = ?", params=[snap.snapshot_id])  # type: ignore[return-value]

    def prev_clientes(self) -> list[Cliente]:
        """Clientes of the most recent ARCHIVED snapshot (for segment growth), or []."""
        snap = self.get_previous_snapshot()
        if snap is None:
            return []
        return self._select(Cliente, "clientes", where="snapshot_id = ?", params=[snap.snapshot_id])  # type: ignore[return-value]

    def prev_cuotas(self) -> list[Cuota]:
        """Cuotas of the most recent ARCHIVED snapshot (for mora trend), or []."""
        snap = self.get_previous_snapshot()
        if snap is None:
            return []
        return self._select(Cuota, "cuotas", where="snapshot_id = ?", params=[snap.snapshot_id])  # type: ignore[return-value]

    def has_siniestros(self) -> bool:
        n = self._con.execute(
            "SELECT count(*) FROM siniestros WHERE snapshot_id = ?", [self._active_id()]
        ).fetchone()[0]
        return n > 0

    # --- HITL inbox (acciones) -------------------------------------------- #
    def add_accion(self, accion: Accion) -> None:
        self._insert("acciones", accion)

    def list_acciones(
        self, *, estado: EstadoAccion | None = None, run_id: str | None = None
    ) -> list[Accion]:
        clauses, params = [], []
        if estado is not None:
            clauses.append("estado = ?")
            params.append(estado.value)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        where = " AND ".join(clauses) if clauses else None
        return self._select(Accion, "acciones", where=where, params=params, order_by="creada_en")

    def get_accion(self, accion_id: str) -> Accion | None:
        rows = self._select(Accion, "acciones", where="accion_id = ?", params=[accion_id])
        return rows[0] if rows else None

    def resolve_accion(self, accion: Accion) -> None:
        self._con.execute(
            """
            UPDATE acciones
               SET estado = ?, mensaje_es = ?, resuelta_en = ?, resuelta_por = ?,
                   nota_revisor = ?
             WHERE accion_id = ?
            """,
            [
                accion.estado.value,
                accion.mensaje_es,
                accion.resuelta_en,
                accion.resuelta_por,
                accion.nota_revisor,
                accion.accion_id,
            ],
        )

    # --- agent runs -------------------------------------------------------- #
    def add_run(self, run: AgentRun) -> None:
        self._insert("agent_runs", run)

    def update_run(self, run: AgentRun) -> None:
        self._con.execute(
            "UPDATE agent_runs SET finalizado_en = ?, estado = ?, resumen_json = ? WHERE run_id = ?",
            [run.finalizado_en, run.estado.value, run.resumen_json, run.run_id],
        )

    # --- audit log (append-only, hash-chained) ----------------------------- #
    def _next_audit_seq(self) -> int:
        row = self._con.execute("SELECT max(seq) FROM audit_log").fetchone()
        return 0 if row[0] is None else int(row[0]) + 1

    def append_audit(self, event: AuditEvent) -> None:
        seq = self._next_audit_seq()
        cols = ["seq"] + _model_columns(AuditEvent)
        values = [seq] + [_to_db(getattr(event, c)) for c in _model_columns(AuditEvent)]
        placeholders = ", ".join(["?"] * len(cols))
        self._con.execute(
            f"INSERT INTO audit_log ({', '.join(cols)}) VALUES ({placeholders})", values
        )

    def last_audit(self) -> AuditEvent | None:
        rows = self._select_audit(where=None, params=[], order_by="seq DESC", limit=1)
        return rows[0] if rows else None

    def read_audit(self) -> list[AuditEvent]:
        return self._select_audit(where=None, params=[], order_by="seq ASC")

    def audit_count(self) -> int:
        return int(self._con.execute("SELECT count(*) FROM audit_log").fetchone()[0])

    # --- ingestion support: materialize a snapshot ------------------------- #
    def materialize_snapshot(self, snapshot: DataSnapshot, data: dict[str, list[_Row]]) -> None:
        """Atomically archive the prior active snapshot and write a new one.

        Called only by validated ingestion (§6). The whole write is one
        transaction: a failure leaves the previously-active snapshot intact.
        """
        self._con.execute("BEGIN TRANSACTION")
        try:
            self._con.execute(
                "UPDATE data_snapshots SET estado = ? WHERE estado = ?",
                [EstadoSnapshot.archivado.value, EstadoSnapshot.activo.value],
            )
            self._insert("data_snapshots", snapshot)
            for table in OPERATIONAL_TABLES:
                for row in data.get(table, []):
                    self._insert_operational(table, row, snapshot.snapshot_id)
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        finally:
            self._active_resolved = False  # invalidate cache

    # --- low-level helpers ------------------------------------------------- #
    def _insert(self, table: str, row: _Row) -> None:
        cols = _model_columns(type(row))
        values = [_to_db(getattr(row, c)) for c in cols]
        placeholders = ", ".join(["?"] * len(cols))
        self._con.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", values
        )

    def _insert_operational(self, table: str, row: _Row, snapshot_id: str) -> None:
        cols = ["snapshot_id"] + _model_columns(type(row))
        values = [snapshot_id] + [_to_db(getattr(row, c)) for c in _model_columns(type(row))]
        placeholders = ", ".join(["?"] * len(cols))
        self._con.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})", values
        )

    def _select(
        self,
        model_cls: type[_Row],
        table: str,
        *,
        where: str | None = None,
        params: list | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[_Row]:
        cols = _model_columns(model_cls)
        sql = f"SELECT {', '.join(cols)} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._con.execute(sql, params or []).fetchall()
        return [model_cls(**dict(zip(cols, r, strict=True))) for r in rows]

    def _select_audit(
        self, *, where: str | None, params: list, order_by: str, limit: int | None = None
    ) -> list[AuditEvent]:
        # audit_log has an extra leading `seq` column not on the model.
        return self._select(
            AuditEvent, "audit_log", where=where, params=params, order_by=order_by, limit=limit
        )
