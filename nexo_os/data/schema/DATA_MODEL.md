# DATA_MODEL.md - the canonical schema (single source of truth)

> Phase 0 stub. Fully populated in Phase 1 alongside the pydantic models and the
> DuckDB DDL in this directory. This schema is the contract for three things at
> once: the Excel template (§6), the local store, and the agents (§4).

Everything downstream reads **typed objects**, never loose dicts. Names are
snake_case, domain terms are Spanish, grain is stated per table, PII is flagged.

## Operational tables (the workbook sheets the broker fills)

- `clientes` - grain: client. PII: nombre, documento, fecha_nacimiento, email, telefono.
- `polizas` - grain: policy. Renewal chains via `poliza_origen_id`.
- `cuotas` - grain: installment. `dias_mora`/`bucket_mora` are **derived at read-time**
  vs `snapshot_fecha`, never stored.
- `comisiones` - grain: policy x period. `diferencia_ars` is derived, not stored.
- `leads` - grain: lead. PII: nombre_prospecto, contacto.
- `cotizaciones` - grain: quote. `poliza_id` set when bound (makes quote-to-bind
  deterministic).
- `aseguradoras` - reference (commission terms by ramo).
- `productores` - broker seats.
- `siniestros` - optional; renewal risk degrades gracefully when absent.

## System tables (written by Nexo, local store, not in the workbook)

- `data_snapshots` - one row per successful upload; exactly one `activo`.
- `acciones` - the HITL inbox.
- `agent_runs` - one row per orchestrator cycle.
- `audit_log` - append-only, hash-chained (tamper-evident).

See §4 of the build brief for the full column list, grains, PII flags, and the
optional-siniestros behavior, which this document will mirror in Phase 1.
