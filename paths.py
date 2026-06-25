"""
paths.py - Canonical filesystem paths for Nexo (single source of truth).

Every module derives its paths from here so the data file, the generated Excel,
the shared-state JSON and the audit trail are never spelled out twice. paths.py
sits at the repository root, so REPO_ROOT is THIS repo's own root and the .env
holding ANTHROPIC_API_KEY is expected at <repo>/.env.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))          # repo root (paths.py lives here)
REPO_ROOT = HERE                                           # this repo's root (standalone)
ENV_PATH = os.path.join(REPO_ROOT, ".env")                 # <repo>/.env (ANTHROPIC_API_KEY)

DATA_DIR = os.path.join(HERE, "data")
OUTPUTS_DIR = os.path.join(HERE, "outputs")

DEMO_CARTERA = os.path.join(DATA_DIR, "cartera_demo.xlsx")     # committed synthetic fixture
STATE_PATH = os.path.join(HERE, "nexo_state.json")            # CarteraContext persistence
AUDIT_PATH = os.path.join(HERE, "audit_log.jsonl")           # append-only audit trail
APPROVED_XLSX = os.path.join(OUTPUTS_DIR, "acciones_aprobadas.xlsx")


def ensure_dirs():
    """Create the data/ and outputs/ directories if they do not exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
