-- Nexo Operating Model v3 - canonical local store DDL (DuckDB dialect).
-- Single source of truth for the store, mirrored by the pydantic models in
-- models.py and documented in DATA_MODEL.md.
--
-- Money is DECIMAL (never float): ARS amounts DECIMAL(18,2), percentages
-- DECIMAL(9,6). Derived quantities (dias_mora, bucket_mora, diferencia_ars) are
-- NOT stored - they are computed at read-time vs the active snapshot's date.
--
-- Snapshot scoping: every OPERATIONAL row carries snapshot_id, and its primary
-- key is composite (snapshot_id, <natural_pk>). Exactly one snapshot is `activo`.
-- Referential integrity is enforced fail-closed at INGESTION (see ingest.py),
-- not via DB-level foreign keys, because RI must hold within a snapshot before
-- a row is ever written.

-- ===================== System tables (written by Nexo) ===================== --

CREATE TABLE IF NOT EXISTS data_snapshots (
    snapshot_id      VARCHAR PRIMARY KEY,
    snapshot_fecha   DATE        NOT NULL,
    archivo_nombre   VARCHAR     NOT NULL,
    archivo_hash     VARCHAR     NOT NULL,
    cargado_por      VARCHAR     NOT NULL,
    cargado_en       TIMESTAMP   NOT NULL,
    row_counts_json  VARCHAR     NOT NULL,
    estado           VARCHAR     NOT NULL   -- activo | archivado
);

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id        VARCHAR PRIMARY KEY,
    iniciado_en   TIMESTAMP   NOT NULL,
    finalizado_en TIMESTAMP,
    estado        VARCHAR     NOT NULL,     -- ok | con_warnings | error
    resumen_json  VARCHAR     NOT NULL,
    snapshot_id   VARCHAR     NOT NULL
);

CREATE TABLE IF NOT EXISTS acciones (
    accion_id          VARCHAR PRIMARY KEY,
    agente             VARCHAR     NOT NULL,
    tipo_accion        VARCHAR     NOT NULL,
    entidad_tipo       VARCHAR     NOT NULL,
    entidad_id         VARCHAR     NOT NULL,
    prioridad          VARCHAR     NOT NULL,   -- alta | media | baja
    confianza          DOUBLE      NOT NULL,   -- 0..1, deterministic
    monto_en_juego_ars DECIMAL(18,2),          -- nullable (no natural amount)
    rationale_json     VARCHAR     NOT NULL,
    mensaje_es         VARCHAR     NOT NULL,
    estado             VARCHAR     NOT NULL,   -- propuesta|aprobada|rechazada|editada|vencida
    creada_en          TIMESTAMP   NOT NULL,
    resuelta_en        TIMESTAMP,
    resuelta_por       VARCHAR,
    nota_revisor       VARCHAR,
    run_id             VARCHAR     NOT NULL,
    snapshot_id        VARCHAR     NOT NULL
);

-- Append-only + hash-chained. Application code must never UPDATE/DELETE rows here.
CREATE TABLE IF NOT EXISTS audit_log (
    seq          BIGINT      NOT NULL,        -- monotonic chain order
    evento_id    VARCHAR PRIMARY KEY,
    ts           TIMESTAMP   NOT NULL,
    actor        VARCHAR     NOT NULL,
    accion       VARCHAR     NOT NULL,
    entidad_tipo VARCHAR,
    entidad_id   VARCHAR,
    detalle_json VARCHAR     NOT NULL,        -- identifiers only, NEVER full PII
    prev_hash    VARCHAR,
    hash         VARCHAR     NOT NULL
);

-- Broker seats with hashed credentials + role (auth/RBAC). System table.
CREATE TABLE IF NOT EXISTS usuarios (
    usuario       VARCHAR PRIMARY KEY,
    nombre        VARCHAR     NOT NULL,
    rol           VARCHAR     NOT NULL,   -- admin | operador
    password_hash VARCHAR     NOT NULL,   -- bcrypt; plaintext is never stored
    activo        BOOLEAN     NOT NULL,
    creado_en     TIMESTAMP   NOT NULL
);

-- ===================== Operational tables (workbook sheets) ================ --

CREATE TABLE IF NOT EXISTS clientes (
    snapshot_id      VARCHAR NOT NULL,
    cliente_id       VARCHAR NOT NULL,
    tipo             VARCHAR NOT NULL,
    nombre           VARCHAR NOT NULL,        -- PII
    documento        VARCHAR NOT NULL,        -- PII
    email            VARCHAR,                 -- PII
    telefono         VARCHAR,                 -- PII
    fecha_nacimiento DATE,                    -- PII
    localidad        VARCHAR,
    provincia        VARCHAR,
    segmento         VARCHAR,
    fecha_alta       DATE,
    productor_id     VARCHAR NOT NULL,
    estado           VARCHAR NOT NULL,        -- activo | inactivo
    PRIMARY KEY (snapshot_id, cliente_id)
);

CREATE TABLE IF NOT EXISTS polizas (
    snapshot_id           VARCHAR NOT NULL,
    poliza_id             VARCHAR NOT NULL,
    nro_poliza            VARCHAR NOT NULL,
    cliente_id            VARCHAR NOT NULL,
    aseguradora_id        VARCHAR NOT NULL,
    ramo                  VARCHAR NOT NULL,
    fecha_inicio_vigencia DATE    NOT NULL,
    fecha_fin_vigencia    DATE    NOT NULL,
    prima_ars             DECIMAL(18,2) NOT NULL,
    suma_asegurada_ars    DECIMAL(18,2),
    estado                VARCHAR NOT NULL,
    forma_pago            VARCHAR,
    frecuencia_pago       VARCHAR NOT NULL,
    comision_pct          DECIMAL(9,6) NOT NULL,
    productor_id          VARCHAR NOT NULL,
    poliza_origen_id      VARCHAR,
    PRIMARY KEY (snapshot_id, poliza_id)
);

CREATE TABLE IF NOT EXISTS cuotas (
    snapshot_id      VARCHAR NOT NULL,
    cuota_id         VARCHAR NOT NULL,
    poliza_id        VARCHAR NOT NULL,
    nro_cuota        INTEGER NOT NULL,
    fecha_vencimiento DATE   NOT NULL,
    monto_ars        DECIMAL(18,2) NOT NULL,
    estado           VARCHAR NOT NULL,
    fecha_pago       DATE,
    monto_pagado_ars DECIMAL(18,2),
    PRIMARY KEY (snapshot_id, cuota_id)
);

CREATE TABLE IF NOT EXISTS comisiones (
    snapshot_id            VARCHAR NOT NULL,
    comision_id            VARCHAR NOT NULL,
    poliza_id              VARCHAR NOT NULL,
    aseguradora_id         VARCHAR NOT NULL,
    periodo                VARCHAR NOT NULL,   -- YYYY-MM
    base_comisionable_ars  DECIMAL(18,2) NOT NULL,
    comision_pct           DECIMAL(9,6) NOT NULL,
    comision_esperada_ars  DECIMAL(18,2) NOT NULL,
    comision_liquidada_ars DECIMAL(18,2),
    fecha_liquidacion      DATE,
    estado                 VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_id, comision_id)
);

CREATE TABLE IF NOT EXISTS leads (
    snapshot_id            VARCHAR NOT NULL,
    lead_id                VARCHAR NOT NULL,
    fecha_ingreso          DATE    NOT NULL,
    nombre_prospecto       VARCHAR NOT NULL,   -- PII
    contacto               VARCHAR,            -- PII
    canal_origen           VARCHAR NOT NULL,
    ramo                   VARCHAR NOT NULL,
    productor_id           VARCHAR NOT NULL,
    estado                 VARCHAR NOT NULL,
    fecha_ultimo_movimiento DATE,
    fecha_cierre           DATE,
    motivo_perdida         VARCHAR,
    cliente_id             VARCHAR,
    PRIMARY KEY (snapshot_id, lead_id)
);

CREATE TABLE IF NOT EXISTS cotizaciones (
    snapshot_id        VARCHAR NOT NULL,
    cotizacion_id      VARCHAR NOT NULL,
    lead_id            VARCHAR NOT NULL,
    aseguradora_id     VARCHAR NOT NULL,
    ramo               VARCHAR NOT NULL,
    prima_cotizada_ars DECIMAL(18,2) NOT NULL,
    fecha_cotizacion   DATE    NOT NULL,
    estado             VARCHAR NOT NULL,
    vigencia_cotizacion DATE,
    poliza_id          VARCHAR,
    PRIMARY KEY (snapshot_id, cotizacion_id)
);

CREATE TABLE IF NOT EXISTS aseguradoras (
    snapshot_id              VARCHAR NOT NULL,
    aseguradora_id           VARCHAR NOT NULL,
    nombre                   VARCHAR NOT NULL,
    condiciones_comision_json VARCHAR,
    PRIMARY KEY (snapshot_id, aseguradora_id)
);

CREATE TABLE IF NOT EXISTS productores (
    snapshot_id  VARCHAR NOT NULL,
    productor_id VARCHAR NOT NULL,
    nombre       VARCHAR NOT NULL,
    equipo       VARCHAR,
    activo       BOOLEAN NOT NULL,
    PRIMARY KEY (snapshot_id, productor_id)
);

CREATE TABLE IF NOT EXISTS siniestros (
    snapshot_id         VARCHAR NOT NULL,
    siniestro_id        VARCHAR NOT NULL,
    poliza_id           VARCHAR NOT NULL,
    fecha               DATE    NOT NULL,
    tipo                VARCHAR NOT NULL,
    monto_reclamado_ars DECIMAL(18,2) NOT NULL,
    monto_pagado_ars    DECIMAL(18,2),
    estado              VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_id, siniestro_id)
);
