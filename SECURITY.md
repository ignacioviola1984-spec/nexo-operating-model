# SECURITY.md - Nexo Operating Model v3

This file is the single place that documents what data exists, where it lives,
what is sent to the model, and the retention/backup stance.

## Threat model in one line

Real client PII and money figures live on a **local** machine. No cloud, no
outbound execution. The risks we mitigate: a wrong-but-confident number, an
unapproved action, PII leaking to the model or logs, and silent loss/tampering of
the approval+audit history.

## Where data lives (system of record)

- Uploaded workbooks are validated and snapshotted into a local **DuckDB** store at
  `nexo_os/data/store/nexo.duckdb` (gitignored). Exactly one snapshot is active.
- Approvals, the HITL inbox, agent runs, and the **hash-chained audit log** live
  **only** in the local store. They are NOT in the uploaded workbook and there is
  no cloud backup. Losing the store loses the approval/audit history -> see Backup.

## What is sent to the model

- Only the **narrate** step calls Claude, and only to write Spanish prose given
  numbers the deterministic core already computed. The model never produces a
  figure (enforced by the grounding guard) and receives **minimized PII**: first
  names/identifiers, never full `documento`, `email`, `telefono`, or
  `fecha_nacimiento`. (Redaction helper + PII-minimization eval, §16.)
- Offline by default: with `NEXO_USE_LLM=0` no data leaves the machine at all.

## Secrets

- All secrets via repo-root `.env` (gitignored before first commit) + pydantic
  settings. `.env.example` documents the keys with empty values. Use a fresh
  Anthropic key dedicated to Nexo.

## Auth / RBAC (Phase 7)

- Hashed credentials (bcrypt), sessions expire, no anonymous access. Roles:
  `admin` (uploads, user mgmt, all views) and `operador` (inbox + views).
- First boot: `make bootstrap-admin` provisions one admin from `.env`. No anonymous
  fallback, ever.

## Audit integrity

- `audit_log` is append-only and hash-chained: each row hashes over the prior
  row's hash, so tampering is **detectable**. This is tamper-**evident**, not
  access control - it detects a break, it does not physically prevent one.

## Backup (the only safety net for the system of record)

The approval/audit history lives ONLY in the local store - there is no cloud
backup. Losing the store loses that history. Therefore:

- `make backup` writes a timestamped copy to `backups/` (after a DuckDB
  CHECKPOINT, so it is consistent). `make restore FILE=...` restores it.
- The admin UI (Carga de datos) shows the **last backup date** and offers a
  "Crear backup ahora" button.
- **Routine:** run `make backup` after each upload + review session (or schedule a
  daily local copy). Keep backups **off this machine** and **encrypted/protected**
  - they contain client PII. Never commit backups (the `backups/` dir is
  gitignored). Test `make restore` periodically.

## Execution seam (disabled)

- A single `NoopExecutionAdapter` only records "would execute" to the audit log.
  Nothing is sent or written to any external system in this build.
