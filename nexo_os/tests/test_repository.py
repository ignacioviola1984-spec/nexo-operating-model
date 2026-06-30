"""Phase 1 contract tests: schema round-trips, snapshot scoping, system tables.

The key property under test: agent-facing reads return typed objects with money
as Decimal, scoped to the single active snapshot, regardless of how data arrived.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from nexo_os.data import store as store_mod
from nexo_os.data.schema.models import (
    Accion,
    AgentRun,
    Aseguradora,
    AuditEvent,
    Cliente,
    DataSnapshot,
    EstadoAccion,
    EstadoCliente,
    EstadoRun,
    EstadoSnapshot,
    Poliza,
    Prioridad,
    Productor,
)
from nexo_os.data.snapshot_repository import SnapshotRepository


# --------------------------- builders --------------------------------------- #
def _snapshot(
    sid: str, fecha: date, estado: EstadoSnapshot = EstadoSnapshot.activo
) -> DataSnapshot:
    return DataSnapshot(
        snapshot_id=sid,
        snapshot_fecha=fecha,
        archivo_nombre=f"{sid}.xlsx",
        archivo_hash="deadbeef",
        cargado_por="admin",
        cargado_en=datetime(2026, 6, 29, 10, 0, 0),
        row_counts_json=json.dumps({"clientes": 1}),
        estado=estado,
    )


def _cliente(cid: str) -> Cliente:
    return Cliente(
        cliente_id=cid,
        tipo="persona_fisica",
        nombre="Cliente Falso",
        documento="20-00000000-0",
        email="falso@example.com",
        productor_id="P1",
        estado=EstadoCliente.activo,
    )


def _poliza(pid: str, cid: str) -> Poliza:
    return Poliza(
        poliza_id=pid,
        nro_poliza=f"NRO-{pid}",
        cliente_id=cid,
        aseguradora_id="A1",
        ramo="auto",
        fecha_inicio_vigencia=date(2026, 1, 1),
        fecha_fin_vigencia=date(2026, 12, 31),
        prima_ars=Decimal("123456.78"),
        estado="vigente",
        frecuencia_pago="mensual",
        comision_pct=Decimal("0.155000"),
        productor_id="P1",
    )


def _refs() -> dict[str, list]:
    return {
        "clientes": [_cliente("C1")],
        "polizas": [_poliza("POL1", "C1")],
        "aseguradoras": [Aseguradora(aseguradora_id="A1", nombre="Aseg Falsa")],
        "productores": [Productor(productor_id="P1", nombre="Prod Falso", activo=True)],
    }


@pytest.fixture()
def repo(tmp_path):
    con = store_mod.connect(tmp_path / "nexo.duckdb")
    r = SnapshotRepository(con)
    yield r
    r.close()


# --------------------------- tests ------------------------------------------ #
def test_empty_store_has_no_active_snapshot(repo):
    assert repo.active_snapshot() is None
    assert repo.get_previous_snapshot() is None
    with pytest.raises(RuntimeError):
        _ = repo.snapshot_fecha


def test_materialize_and_typed_reads_preserve_decimal(repo):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 6, 30)), _refs())
    assert repo.snapshot_fecha == date(2026, 6, 30)

    polizas = repo.get_polizas()
    assert len(polizas) == 1
    p = polizas[0]
    assert isinstance(p.prima_ars, Decimal)
    assert p.prima_ars == Decimal("123456.78")
    assert p.comision_pct == Decimal("0.155000")
    assert p.ramo == "auto"  # StrEnum round-trips

    clientes = repo.get_clientes()
    assert clientes[0].cliente_id == "C1"
    assert clientes[0].estado == EstadoCliente.activo


def test_second_snapshot_archives_the_first(repo):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 5, 31)), _refs())
    repo.materialize_snapshot(_snapshot("S2", date(2026, 6, 30)), _refs())

    active = repo.active_snapshot()
    assert active is not None and active.snapshot_id == "S2"
    prev = repo.get_previous_snapshot()
    assert prev is not None and prev.snapshot_id == "S1"
    assert prev.estado == EstadoSnapshot.archivado
    # Reads are scoped to the active snapshot only.
    assert {p.poliza_id for p in repo.get_polizas()} == {"POL1"}
    assert len(repo.get_polizas()) == 1


def test_optional_siniestros_absent(repo):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 6, 30)), _refs())
    assert repo.get_siniestros() == []
    assert repo.has_siniestros() is False


def test_acciones_lifecycle(repo):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 6, 30)), _refs())
    accion = Accion(
        accion_id="ACC1",
        agente="cobranza",
        tipo_accion="gestion_cobranza",
        entidad_tipo="cuota",
        entidad_id="Q1",
        prioridad=Prioridad.alta,
        confianza=0.92,
        monto_en_juego_ars=Decimal("50000.00"),
        rationale_json=json.dumps({"monto": "50000.00"}),
        mensaje_es="Mensaje de prueba.",
        creada_en=datetime(2026, 6, 29, 12, 0, 0),
        run_id="RUN1",
        snapshot_id="S1",
    )
    repo.add_accion(accion)
    assert len(repo.list_acciones(estado=EstadoAccion.propuesta)) == 1

    fetched = repo.get_accion("ACC1")
    assert fetched is not None and fetched.confianza == pytest.approx(0.92)
    assert fetched.monto_en_juego_ars == Decimal("50000.00")

    fetched.estado = EstadoAccion.aprobada
    fetched.resuelta_en = datetime(2026, 6, 29, 13, 0, 0)
    fetched.resuelta_por = "operador1"
    fetched.nota_revisor = "ok"
    repo.resolve_accion(fetched)

    assert repo.list_acciones(estado=EstadoAccion.propuesta) == []
    approved = repo.list_acciones(estado=EstadoAccion.aprobada)
    assert len(approved) == 1 and approved[0].resuelta_por == "operador1"


def test_accion_with_null_amount(repo):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 6, 30)), _refs())
    accion = Accion(
        accion_id="ACC2",
        agente="comercial",
        tipo_accion="limpieza_funnel",
        entidad_tipo="lead",
        entidad_id="L1",
        prioridad=Prioridad.baja,
        confianza=0.5,
        monto_en_juego_ars=None,  # no natural amount
        rationale_json="{}",
        mensaje_es="Sin monto.",
        creada_en=datetime(2026, 6, 29, 12, 0, 0),
        run_id="RUN1",
        snapshot_id="S1",
    )
    repo.add_accion(accion)
    assert repo.get_accion("ACC2").monto_en_juego_ars is None


def test_agent_run_persisted(repo):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 6, 30)), _refs())
    run = AgentRun(
        run_id="RUN1",
        iniciado_en=datetime(2026, 6, 29, 12, 0, 0),
        estado=EstadoRun.ok,
        resumen_json="{}",
        snapshot_id="S1",
    )
    repo.add_run(run)
    run.finalizado_en = datetime(2026, 6, 29, 12, 5, 0)
    run.estado = EstadoRun.con_warnings
    repo.update_run(run)


def test_audit_append_only_and_ordered(repo):
    e1 = AuditEvent(
        evento_id="E1",
        ts=datetime(2026, 6, 29, 12, 0, 0),
        actor="admin",
        accion="upload",
        detalle_json=json.dumps({"snapshot_id": "S1"}),
        prev_hash=None,
        hash="h1",
    )
    e2 = AuditEvent(
        evento_id="E2",
        ts=datetime(2026, 6, 29, 12, 1, 0),
        actor="operador1",
        accion="approve",
        detalle_json=json.dumps({"accion_id": "ACC1"}),
        prev_hash="h1",
        hash="h2",
    )
    repo.append_audit(e1)
    repo.append_audit(e2)
    events = repo.read_audit()
    assert [e.evento_id for e in events] == ["E1", "E2"]
    assert repo.last_audit().evento_id == "E2"
    assert events[1].prev_hash == "h1"


def test_backup_and_restore_roundtrip(repo, tmp_path):
    repo.materialize_snapshot(_snapshot("S1", date(2026, 6, 30)), _refs())
    store_path = tmp_path / "nexo.duckdb"
    repo.close()

    backup_dir = tmp_path / "backups"
    dest = store_mod.backup(store_path, backup_dir, stamp="20260629-000000")
    assert dest.exists()
    assert store_mod.last_backup(backup_dir) == dest

    # Wipe + restore.
    store_path.unlink()
    store_mod.restore(dest, store_path)
    r2 = SnapshotRepository.open(store_path)
    try:
        assert r2.active_snapshot().snapshot_id == "S1"
        assert len(r2.get_polizas()) == 1
    finally:
        r2.close()
