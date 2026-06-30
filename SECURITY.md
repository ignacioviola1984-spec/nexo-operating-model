# SECURITY.md - Nexo Operating Model v3

> Phase 0 stub. Filled out in Phase 9 (hardening). This file is the single place
> that documents what data exists, where it lives, what is sent to the model, and
> the retention/backup stance.

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

## Backup (Phase 1/9)

- `make backup` / `make restore` snapshot the local store. Keep backups off-repo
  and protected (they contain PII). The admin UI surfaces the last backup date.

## Execution seam (disabled)

- A single `NoopExecutionAdapter` only records "would execute" to the audit log.
  Nothing is sent or written to any external system in this build.
