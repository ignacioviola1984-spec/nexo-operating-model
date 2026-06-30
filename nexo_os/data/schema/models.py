"""Canonical typed domain model for Nexo v3 (the §4 schema).

This is the contract for three things at once: the Excel template, the local
DuckDB store, and the agents. Everything downstream reads these typed objects,
never loose dicts. Money is `Decimal` (never float); ARS unless a field says
otherwise. Derived quantities (dias_mora, bucket_mora, diferencia_ars) are NOT
stored here - they are computed at read-time vs the active snapshot's date.

PII fields are flagged in `PII_FIELDS` (used by the redaction helper + the
PII-minimization eval). Snapshot scoping (`snapshot_id`) is a storage concern and
lives in the DDL / repository, not on these domain rows.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Enums (the validated domain vocabularies; also drive the template dropdowns)
# --------------------------------------------------------------------------- #
class TipoCliente(StrEnum):
    persona_fisica = "persona_fisica"
    persona_juridica = "persona_juridica"


class EstadoCliente(StrEnum):
    activo = "activo"
    inactivo = "inactivo"


class Ramo(StrEnum):
    auto = "auto"
    hogar = "hogar"
    vida = "vida"
    art = "art"
    caucion = "caucion"
    accidentes_personales = "accidentes_personales"
    comercio = "comercio"
    otros = "otros"


class EstadoPoliza(StrEnum):
    vigente = "vigente"
    vencida = "vencida"
    anulada = "anulada"
    en_gestion = "en_gestion"
    renovada = "renovada"


class FrecuenciaPago(StrEnum):
    mensual = "mensual"
    trimestral = "trimestral"
    semestral = "semestral"
    anual = "anual"


class EstadoCuota(StrEnum):
    pendiente = "pendiente"
    pagada = "pagada"
    vencida = "vencida"
    parcial = "parcial"


class EstadoComision(StrEnum):
    esperada = "esperada"
    liquidada = "liquidada"
    parcial = "parcial"
    con_diferencia = "con_diferencia"


class CanalOrigen(StrEnum):
    referido = "referido"
    web = "web"
    redes = "redes"
    llamado = "llamado"
    otro = "otro"


class EstadoLead(StrEnum):
    nuevo = "nuevo"
    contactado = "contactado"
    cotizado = "cotizado"
    presentado = "presentado"
    ganado = "ganado"
    perdido = "perdido"


class EstadoCotizacion(StrEnum):
    emitida = "emitida"
    presentada = "presentada"
    aceptada = "aceptada"
    rechazada = "rechazada"
    vencida = "vencida"


class EstadoSiniestro(StrEnum):
    abierto = "abierto"
    en_analisis = "en_analisis"
    pagado = "pagado"
    rechazado = "rechazado"
    cerrado = "cerrado"


class BucketMora(StrEnum):
    """Aging bucket - DERIVED at read-time vs snapshot_fecha, never stored."""

    al_dia = "0"
    b1_30 = "1-30"
    b31_60 = "31-60"
    b61_90 = "61-90"
    b90_plus = "90+"


# Snapshot lifecycle + HITL action / run / audit states (system tables).
class EstadoSnapshot(StrEnum):
    activo = "activo"
    archivado = "archivado"


class Prioridad(StrEnum):
    alta = "alta"
    media = "media"
    baja = "baja"


class EstadoAccion(StrEnum):
    propuesta = "propuesta"
    aprobada = "aprobada"
    rechazada = "rechazada"
    editada = "editada"
    vencida = "vencida"


class EstadoRun(StrEnum):
    ok = "ok"
    con_warnings = "con_warnings"
    error = "error"


class Rol(StrEnum):
    admin = "admin"  # uploads, user mgmt, all views
    operador = "operador"  # operate the inbox + views


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class _Row(BaseModel):
    """Shared config: strict-ish, immutable rows that round-trip cleanly."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
        use_enum_values=False,
    )


# --------------------------------------------------------------------------- #
# Operational tables (the workbook sheets the broker fills)
# --------------------------------------------------------------------------- #
class Cliente(_Row):
    """Grain: client."""

    cliente_id: str
    tipo: TipoCliente
    nombre: str  # PII
    documento: str  # PII (CUIT/DNI)
    email: str | None = None  # PII
    telefono: str | None = None  # PII
    fecha_nacimiento: date | None = None  # PII
    localidad: str | None = None
    provincia: str | None = None
    segmento: str | None = None
    fecha_alta: date | None = None
    productor_id: str
    estado: EstadoCliente


class Poliza(_Row):
    """Grain: policy."""

    poliza_id: str
    nro_poliza: str
    cliente_id: str
    aseguradora_id: str
    ramo: Ramo
    fecha_inicio_vigencia: date
    fecha_fin_vigencia: date
    prima_ars: Decimal
    suma_asegurada_ars: Decimal | None = None
    estado: EstadoPoliza
    forma_pago: str | None = None
    frecuencia_pago: FrecuenciaPago
    comision_pct: Decimal
    productor_id: str
    poliza_origen_id: str | None = None  # prior-term policy (renewal chain)


class Cuota(_Row):
    """Grain: installment. dias_mora/bucket_mora are derived at read-time."""

    cuota_id: str
    poliza_id: str
    nro_cuota: int
    fecha_vencimiento: date
    monto_ars: Decimal
    estado: EstadoCuota
    fecha_pago: date | None = None
    monto_pagado_ars: Decimal | None = None


class Comision(_Row):
    """Grain: policy x period. diferencia_ars is derived (esperada - liquidada)."""

    comision_id: str
    poliza_id: str
    aseguradora_id: str
    periodo: str  # YYYY-MM
    base_comisionable_ars: Decimal
    comision_pct: Decimal
    comision_esperada_ars: Decimal
    comision_liquidada_ars: Decimal | None = None
    fecha_liquidacion: date | None = None
    estado: EstadoComision


class Lead(_Row):
    """Grain: lead."""

    lead_id: str
    fecha_ingreso: date
    nombre_prospecto: str  # PII
    contacto: str | None = None  # PII
    canal_origen: CanalOrigen
    ramo: Ramo
    productor_id: str
    estado: EstadoLead
    fecha_ultimo_movimiento: date | None = None
    fecha_cierre: date | None = None
    motivo_perdida: str | None = None
    cliente_id: str | None = None  # set when won


class Cotizacion(_Row):
    """Grain: quote. poliza_id set when bound (makes quote-to-bind deterministic)."""

    cotizacion_id: str
    lead_id: str
    aseguradora_id: str
    ramo: Ramo
    prima_cotizada_ars: Decimal
    fecha_cotizacion: date
    estado: EstadoCotizacion
    vigencia_cotizacion: date | None = None
    poliza_id: str | None = None  # set when the quote is bound


class Aseguradora(_Row):
    """Reference: insurer + commission terms by ramo."""

    aseguradora_id: str
    nombre: str
    condiciones_comision_json: str | None = None  # JSON: commission terms by ramo


class Productor(_Row):
    """Broker seats / agents."""

    productor_id: str
    nombre: str
    equipo: str | None = None
    activo: bool = True


class Siniestro(_Row):
    """Optional sheet, grain: claim. Used only by Renovaciones risk."""

    siniestro_id: str
    poliza_id: str
    fecha: date
    tipo: str
    monto_reclamado_ars: Decimal
    monto_pagado_ars: Decimal | None = None
    estado: EstadoSiniestro


# --------------------------------------------------------------------------- #
# System tables (written by Nexo; local store; NOT in the workbook)
# --------------------------------------------------------------------------- #
class DataSnapshot(_Row):
    """One row per successful upload. Exactly one is `activo` at a time."""

    snapshot_id: str
    snapshot_fecha: date
    archivo_nombre: str
    archivo_hash: str
    cargado_por: str
    cargado_en: datetime
    row_counts_json: str
    estado: EstadoSnapshot


class Accion(_Row):
    """The HITL inbox row (maker = agent, checker = broker)."""

    accion_id: str
    agente: str
    tipo_accion: str
    entidad_tipo: str
    entidad_id: str
    prioridad: Prioridad
    confianza: float = Field(ge=0.0, le=1.0)
    monto_en_juego_ars: Decimal | None = None
    rationale_json: str  # the deterministic numbers behind the action
    mensaje_es: str  # model-drafted Spanish (or deterministic template)
    estado: EstadoAccion = EstadoAccion.propuesta
    creada_en: datetime
    resuelta_en: datetime | None = None
    resuelta_por: str | None = None
    nota_revisor: str | None = None
    run_id: str
    snapshot_id: str


class AgentRun(_Row):
    run_id: str
    iniciado_en: datetime
    finalizado_en: datetime | None = None
    estado: EstadoRun
    resumen_json: str
    snapshot_id: str


class Usuario(_Row):
    """A broker seat. Plaintext passwords are never stored - only the bcrypt hash."""

    usuario: str
    nombre: str
    rol: Rol
    password_hash: str
    activo: bool = True
    creado_en: datetime


class AuditEvent(_Row):
    """Append-only, hash-chained. Each row's hash chains over the prior hash."""

    evento_id: str
    ts: datetime
    actor: str
    accion: str
    entidad_tipo: str | None = None
    entidad_id: str | None = None
    detalle_json: str  # identifiers only - NEVER full PII
    prev_hash: str | None = None
    hash: str


# --------------------------------------------------------------------------- #
# PII registry (single source for redaction + the PII-minimization eval, §16)
# --------------------------------------------------------------------------- #
PII_FIELDS: dict[str, set[str]] = {
    "clientes": {"nombre", "documento", "email", "telefono", "fecha_nacimiento"},
    "leads": {"nombre_prospecto", "contacto"},
}

# The operational sheets the broker fills, in template/ingestion order.
OPERATIONAL_TABLES: tuple[str, ...] = (
    "clientes",
    "polizas",
    "cuotas",
    "comisiones",
    "leads",
    "cotizaciones",
    "aseguradoras",
    "productores",
    "siniestros",
)

# Sheets that may be omitted without failing ingestion (graceful degradation).
OPTIONAL_TABLES: frozenset[str] = frozenset({"siniestros"})

# Map each operational table name to its model (used by ingestion + repository).
MODEL_BY_TABLE: dict[str, type[_Row]] = {
    "clientes": Cliente,
    "polizas": Poliza,
    "cuotas": Cuota,
    "comisiones": Comision,
    "leads": Lead,
    "cotizaciones": Cotizacion,
    "aseguradoras": Aseguradora,
    "productores": Productor,
    "siniestros": Siniestro,
}
