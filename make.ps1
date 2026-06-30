<#
  Nexo Operating Model v3 - Windows task runner (PowerShell).
  Mirrors the Makefile targets for machines without GNU make.

  Usage:
    ./make.ps1 install
    ./make.ps1 template
    ./make.ps1 seed
    ./make.ps1 ingest path\to\workbook.xlsx
    ./make.ps1 bootstrap-admin
    ./make.ps1 run
    ./make.ps1 test
    ./make.ps1 eval
    ./make.ps1 lint
    ./make.ps1 fmt
    ./make.ps1 backup
    ./make.ps1 restore backups\nexo-YYYYMMDD.duckdb
#>
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)

$PY = ".\.venv\Scripts\python.exe"

switch ($Target) {
    "install" {
        python -m venv .venv
        & $PY -m pip install --upgrade pip
        & $PY -m pip install -r requirements-v3.txt
        & $PY -m pip install -e .
    }
    "template"        { & $PY -m nexo_os.cli template }
    "seed"            { & $PY -m nexo_os.cli seed }
    "ingest"          { & $PY -m nexo_os.cli ingest $Rest[0] }
    "bootstrap-admin" { & $PY -m nexo_os.cli bootstrap-admin }
    "run"             { & $PY -m streamlit run nexo_os/dashboard/app.py }
    "demo"            { & $PY -m streamlit run nexo_os/dashboard/demo.py }
    "test"            { & $PY -m pytest }
    "eval"            { & $PY -m nexo_os.evals.run_evals }
    "lint"            { & $PY -m ruff check nexo_os; & $PY -m black --check nexo_os }
    "fmt"             { & $PY -m ruff check --fix nexo_os; & $PY -m black nexo_os }
    "backup"          { & $PY -m nexo_os.cli backup }
    "restore"         { & $PY -m nexo_os.cli restore $Rest[0] }
    default           { Write-Error "Unknown target '$Target'. See make.ps1 header for targets." }
}
