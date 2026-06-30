# Superseded designs

## v2 - BigQuery / cloud data path (SUPERSEDED by v3)

**Status: superseded. Do not build.**

v2 specified a cloud data path (BigQuery / hosted database) and a wider ten-agent
surface. It was **rejected by the client** on direct feedback for two reasons:

1. **Too complex** - ten agents and a multi-aseguradora surface were more than the
   single broker needed to operate day to day.
2. **The cloud data path caused operational problems** - dependency on a hosted
   database/internet was a recurring source of friction for a one-broker shop.

**v3 supersedes it** and is deliberately narrower and local (see the repo-root
brief and `README.md`): five agents, the data path is an uploaded **Excel
workbook** validated and snapshotted into a **local DuckDB** store, no cloud
dependency at all, fail-closed ingestion, auth/RBAC, and a hash-chained audit log.

### Note on the v2 spec document

The standalone `nexo-os` repo was extracted from the original `ai-finance-engineering`
monorepo and did not carry a committed v2 BigQuery spec file. This note records the
supersession and the reason. If the original v2 spec is later located, archive the
document verbatim in this directory next to this README - never delete it.
