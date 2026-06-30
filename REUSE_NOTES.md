# REUSE_NOTES - what v3 (`nexo_os/`) reuses from v1

Decision record for §2/§3 of the v3 brief. v1 (the flat modules at the repo root)
is the proven, tested base: Excel ingestion, a Streamlit HITL inbox, deterministic
detection, and a numeric grounding guard. v3 keeps v1 in place and builds a new
production package `nexo_os/` beside it, reusing v1's working parts and hardening
them to the production bar. We do **not** import the finance repo (patterns only).

Verdicts: **AS-IS** = port with minimal change · **PATTERN** = rewrite adapting the
idea to the v3 multi-table schema + DuckDB · **DROP** = not carried.

| v1 file | v3 home | Verdict | Note |
|---|---|---|---|
| `llm.py` (grounding guard) | `nexo_os/agents/narrate.py` + guard | **AS-IS** | `grounding_ok/numbers_in/allowed_forms` are schema-agnostic and are the hard wall for non-negotiable #1. Port verbatim; only `draft()` adapts to the new payloads. |
| `review.py` (maker-checker) | `nexo_os/review.py` | **AS-IS** | `pendiente → aprobada/editada/rechazada` state machine + decision attribution. Add RBAC + DB persistence on top; keep the machine. |
| `shared_state.py` | `nexo_os/state.py` (`NexoContext`) | **PATTERN** | Keep the put/get/flag/audit shape. v3 persists to DuckDB and the audit log is **hash-chained** (new). |
| `app.py` (Streamlit inbox) | `nexo_os/dashboard/` | **AS-IS** (UI extended) | Three-button approve/edit/reject card is exemplary. Add login, upload+validation screen, five agent views, audit view. |
| `report_metrics.py` (PII scan) | `nexo_os/` redaction + metrics | **AS-IS** | `scan_for_pii` / identifier collection is production-grade; reuse for the PII-minimization eval and redaction helper. |
| `cartera_core.py` (detectors) | `nexo_os/core/*.py` | **PATTERN** | Detection logic is sound but assumes a single Policy table and `float`. v3 splits into cartera/renovaciones/cobranza/comisiones/comercial, reads typed objects via the repository, and uses `Decimal`. Keep `confidence()` weighting + mora-bucket logic. |
| `schema.py` (Policy) | `nexo_os/data/schema/` | **PATTERN** | Replace single `Policy` with the 9-table typed model (clientes, polizas, cuotas, comisiones, leads, cotizaciones, aseguradoras, productores, siniestros) + DuckDB DDL. Keep date/iso normalization helpers. |
| the 5 agents | `nexo_os/agents/*.py` | **PATTERN** | New five-agent set (Cartera, Renovaciones, Cobranza+morosidad, Comisiones, Pipeline comercial). Keep compute→propose→narrate shape and confidence/severity scoring. |
| `agent_base.py` | `nexo_os/agents/base.py` | **PATTERN** | Keep `emit()` orchestration (draft → guard → action → inbox); adapt to typed AgentResult/Accion. |
| `nexo_orchestrator.py` | `nexo_os/orchestrator.py` | **PATTERN** | Same flow (load → agents → cross-checks → inbox → HITL → persist). Data source swaps Excel→active snapshot; add reconciliation tolerances + run status. |
| `data/generate_synthetic_cartera.py` | `nexo_os/data/synthetic/generate.py` | **PATTERN** | Expand to fill all 9 sheets with planted ground-truth situations; emit a valid workbook **and** broken-workbook fixtures. PII visibly fake. |
| `evals/run_evals.py` | `nexo_os/evals/` | **PATTERN** | Keep grounding/determinism/scope suites; add ingestion fail-closed, numbers-regression, reconciliation, audit-chain, PII-min, RBAC evals. |
| `outputs/excel_writer.py` | (deferred) | **PATTERN** | v3 has no outbound execution; approved actions are recorded in the store. A read-only export may return later. |
| `cli.py` | `nexo_os/cli.py` | **PATTERN** | New subcommands: template/seed/ingest/bootstrap-admin/run/eval/backup/restore. |
| `paths.py` | `nexo_os/config.py` | **PATTERN** | Folded into pydantic-settings `Settings` (store path, backup dir, thresholds). |
| `report_metrics.py` history aggregation | reused as needed | PATTERN | Anonymized metrics are useful but secondary to the audit/inbox spine. |

## Hardening v3 adds on top of v1

- **Fail-closed ingestion**: whole-file rejection with a Spanish validation report; one
  active immutable snapshot at a time (v1 loaded an Excel directly, no snapshot).
- **Auth + RBAC**: v1 was explicitly "no auth"; v3 has hashed logins, admin/operador
  roles, gated uploads/admin actions.
- **Hash-chained, append-only audit log** (tamper-evident) covering uploads, runs,
  every approval/edit/reject, and logins.
- **Decimal money everywhere** (v1 used float).
- **Cross-agent reconciliations** with configured tolerances.
- **Local DuckDB store** as the system of record + backup/restore.

## Not reused

- Nothing is DROPped wholesale; v1's philosophy (deterministic numbers, grounded
  prose, human approval) is the spine of v3. The finance repo is **not** imported.
