# Nexo Operating Model v3 - task runner.
#
# On Windows without GNU make, use the PowerShell wrapper with the same targets:
#   ./make.ps1 install | template | seed | ingest <wb> | run | bootstrap-admin
#                       | test | eval | lint | backup | restore <file>
#
# All targets run inside the local virtualenv (.venv). No cloud, no network for
# the data path.

PY := .venv/Scripts/python.exe   # Windows venv interpreter; override on POSIX:
                                  #   make PY=.venv/bin/python <target>

.PHONY: install template seed ingest run bootstrap-admin test eval lint fmt backup restore

install:                ## Create/refresh the venv deps from the locked set.
	python -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-v3.txt
	$(PY) -m pip install -e .

template:               ## Emit the blank canonical Excel template.
	$(PY) -m nexo_os.cli template

seed:                   ## Generate the synthetic filled workbook for tests.
	$(PY) -m nexo_os.cli seed

ingest:                 ## Validate + load a workbook: make ingest WB=path/to.xlsx
	$(PY) -m nexo_os.cli ingest "$(WB)"

bootstrap-admin:        ## Provision the first admin from .env.
	$(PY) -m nexo_os.cli bootstrap-admin

run:                    ## Launch the local Streamlit dashboard (production).
	$(PY) -m streamlit run nexo_os/dashboard/app.py

demo:                   ## Launch the public CV/portfolio demo (no login, synthetic).
	$(PY) -m streamlit run nexo_os/dashboard/demo.py

test:                   ## Run the test suite.
	$(PY) -m pytest

eval:                   ## Run the eval / guardrail harness (non-zero on failure).
	$(PY) -m nexo_os.evals.run_evals

lint:                   ## ruff + black --check.
	$(PY) -m ruff check nexo_os
	$(PY) -m black --check nexo_os

fmt:                    ## Auto-format with ruff --fix + black.
	$(PY) -m ruff check --fix nexo_os
	$(PY) -m black nexo_os

backup:                 ## Back up the local store (system of record).
	$(PY) -m nexo_os.cli backup

restore:                ## Restore the local store: make restore FILE=backups/x.duckdb
	$(PY) -m nexo_os.cli restore "$(FILE)"
