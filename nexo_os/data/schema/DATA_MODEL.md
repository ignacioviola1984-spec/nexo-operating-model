# DATA_MODEL.md - the canonical schema (single source of truth)

This schema is the contract for three things at once: the **Excel template** (§6),
the **local DuckDB store**, and the **agents** (§4). It is defined once as typed
pydantic models ([models.py](models.py)) and as the canonical SQL DDL
([schema.sql](schema.sql), DuckDB dialect). Everything downstream reads typed
objects, never loose dicts.

Conventions: snake_case names · Spanish domain terms · **money is `Decimal`**
(`DECIMAL(18,2)` ARS; percentages `DECIMAL(9,6)`), never float · ARS unless a
field says otherwise · PII flagged · derived quantities are **never stored**.

## Storage model: snapshots

Every **operational** row carries a `snapshot_id` and a composite primary key
`(snapshot_id, <natural_pk>)`. Exactly one snapshot is `activo`; uploading a valid
workbook archives the prior one (§6). The active snapshot defines the run's as-of
date (`snapshot_fecha`) - there is no scattered `now()`. Referential integrity is
enforced **fail-closed at ingestion**, before any row is written, not via DB-level
foreign keys.

Derived-at-read-time (NOT columns, so aging never disagrees with the snapshot):
- `cuotas.dias_mora`, `cuotas.bucket_mora` - relative to `snapshot_fecha`.
- `comisiones.diferencia_ars` = `comision_esperada_ars - comision_liquidada_ars`.

---

## Operational tables (the workbook sheets the broker fills)

### `clientes` - grain: client
| column | type | notes |
|---|---|---|
| cliente_id | str PK | |
| tipo | enum | persona_fisica \| persona_juridica |
| nombre | str | **PII** |
| documento | str | **PII** (CUIT/DNI) |
| email | str? | **PII** |
| telefono | str? | **PII** |
| fecha_nacimiento | date? | **PII** |
| localidad, provincia, segmento | str? | |
| fecha_alta | date? | |
| productor_id | str FK | -> productores |
| estado | enum | activo \| inactivo |

### `polizas` - grain: policy
`poliza_id` PK · nro_poliza · cliente_id FK · aseguradora_id FK · ramo (auto \|
hogar \| vida \| art \| caucion \| accidentes_personales \| comercio \| otros) ·
fecha_inicio_vigencia · fecha_fin_vigencia (≥ inicio) · prima_ars · suma_asegurada_ars? ·
estado (vigente \| vencida \| anulada \| en_gestion \| renovada) · forma_pago? ·
frecuencia_pago (mensual \| trimestral \| semestral \| anual) · comision_pct ·
productor_id FK · **poliza_origen_id?** FK -> polizas (prior-term policy; renewal chains).

### `cuotas` - grain: installment
`cuota_id` PK · poliza_id FK · nro_cuota · fecha_vencimiento · monto_ars ·
estado (pendiente \| pagada \| vencida \| parcial) · fecha_pago? · monto_pagado_ars?.
`dias_mora` / `bucket_mora` (0 \| 1-30 \| 31-60 \| 61-90 \| 90+) are **derived**.

### `comisiones` - grain: policy x period
`comision_id` PK · poliza_id FK · aseguradora_id FK · periodo (YYYY-MM) ·
base_comisionable_ars · comision_pct · comision_esperada_ars · comision_liquidada_ars? ·
fecha_liquidacion? · estado (esperada \| liquidada \| parcial \| con_diferencia).
`diferencia_ars` is **derived**. Receivable aging anchors to period-end of `periodo`
plus a configured terms offset, NOT to the nullable `fecha_liquidacion`.

### `leads` - grain: lead
`lead_id` PK · fecha_ingreso · nombre_prospecto (**PII**) · contacto? (**PII**) ·
canal_origen (referido \| web \| redes \| llamado \| otro) · ramo · productor_id FK ·
estado (nuevo \| contactado \| cotizado \| presentado \| ganado \| perdido) ·
fecha_ultimo_movimiento? · fecha_cierre? · motivo_perdida? · cliente_id? FK (set when won).

### `cotizaciones` - grain: quote
`cotizacion_id` PK · lead_id FK · aseguradora_id FK · ramo · prima_cotizada_ars ·
fecha_cotizacion · estado (emitida \| presentada \| aceptada \| rechazada \| vencida) ·
vigencia_cotizacion? · **poliza_id?** FK -> polizas (set when bound; makes quote-to-bind
deterministically computable, §10.5).

### `aseguradoras` - reference
`aseguradora_id` PK · nombre · condiciones_comision_json (commission terms by ramo).

### `productores` - broker seats/agents
`productor_id` PK · nombre · equipo? · activo (bool).

### `siniestros` - OPTIONAL, grain: claim
`siniestro_id` PK · poliza_id FK · fecha · tipo · monto_reclamado_ars ·
monto_pagado_ars? · estado. **Optional**: if the broker omits the sheet, the
Renovaciones risk score degrades gracefully (and says so) - it does not fail.

---

## System tables (written by Nexo; local store; NOT in the workbook)

### `data_snapshots`
One row per successful upload. `snapshot_id` PK · snapshot_fecha · archivo_nombre ·
archivo_hash · cargado_por · cargado_en · row_counts_json · estado (activo \|
archivado). Exactly one `activo` at a time.

### `acciones` - the HITL inbox
`accion_id` PK · agente · tipo_accion · entidad_tipo · entidad_id · prioridad (alta
\| media \| baja) · confianza (0-1, deterministic) · monto_en_juego_ars? ·
rationale_json (the deterministic numbers) · mensaje_es (model-drafted Spanish) ·
estado (propuesta \| aprobada \| rechazada \| editada \| vencida) · creada_en ·
resuelta_en? · resuelta_por? · nota_revisor? · run_id FK · snapshot_id FK.

### `agent_runs`
`run_id` PK · iniciado_en · finalizado_en? · estado (ok \| con_warnings \| error) ·
resumen_json · snapshot_id FK.

### `audit_log` - append-only, hash-chained
`seq` (chain order) · `evento_id` PK · ts · actor · accion · entidad_tipo? ·
entidad_id? · detalle_json (**identifiers only, never full PII**) · prev_hash · hash.
Each row's `hash` chains over the prior row's `hash`, so tampering is **detectable**
(tamper-evident, not access control). Covers uploads, agent runs, every
approval/rejection/edit, and every login. Written only through an append-only writer.

---

## ER overview

```
productores 1───* clientes 1───* polizas 1───* cuotas
                                   │   1───* comisiones
                                   │   1───* siniestros (optional)
                                   └──< poliza_origen_id (self, renewal chain)
aseguradoras 1───* polizas / comisiones / cotizaciones
leads 1───* cotizaciones ───? polizas (poliza_id set when bound)
leads ───? clientes (cliente_id set when won)

system: data_snapshots 1───* {all operational rows, acciones, agent_runs}
        agent_runs 1───* acciones ;  audit_log (chain) spans everything
```
