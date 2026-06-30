"""Nexo v3 command-line entry point.

Thin dispatcher used by the Makefile. Subcommands are wired in as later phases
land (template, seed, ingest, bootstrap-admin, run, eval). Phase 0 ships the
skeleton so the `nexo` entry point resolves and the dispatch surface is fixed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from nexo_os import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nexo", description="Nexo Operating Model v3 (local).")
    p.add_argument("--version", action="version", version=f"nexo {__version__}")
    sub = p.add_subparsers(dest="command", metavar="<command>")

    sub.add_parser("template", help="Emit the blank canonical Excel template.")
    sub.add_parser("seed", help="Generate a synthetic filled workbook for tests.")
    ing = sub.add_parser("ingest", help="Validate + load a workbook into a snapshot.")
    ing.add_argument("workbook", help="Path to the .xlsx workbook to ingest.")
    sub.add_parser("bootstrap-admin", help="Provision the first admin from .env.")
    sub.add_parser("run", help="Run a full agent cycle against the active snapshot.")
    sub.add_parser("eval", help="Run the eval/guardrail harness.")
    sub.add_parser("backup", help="Back up the local store (system of record).")
    res = sub.add_parser("restore", help="Restore the local store from a backup file.")
    res.add_argument("file", help="Path to the backup .duckdb file to restore.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "template":
        return _cmd_template()
    if args.command == "seed":
        return _cmd_seed()
    if args.command == "ingest":
        return _cmd_ingest(args.workbook)
    if args.command == "backup":
        return _cmd_backup()
    if args.command == "restore":
        return _cmd_restore(args.file)

    # Remaining subcommands are wired in as their phases land.
    print(
        f"nexo: command '{args.command}' is scaffolded but not yet wired in this phase.",
        file=sys.stderr,
    )
    return 2


def _cmd_template() -> int:
    from pathlib import Path

    from nexo_os.config import REPO_ROOT
    from nexo_os.data.template import TEMPLATE_NAME, build_template

    dest = Path(REPO_ROOT) / "nexo_os" / "data" / "templates" / TEMPLATE_NAME
    build_template(dest)
    print(f"Plantilla escrita en {dest}")
    return 0


def _cmd_seed() -> int:
    from nexo_os.data.synthetic.generate import generate_all

    written = generate_all()
    for name, path in written.items():
        print(f"{name}: {path}")
    return 0


def _cmd_ingest(workbook: str) -> int:
    from datetime import date, datetime

    from nexo_os.config import get_settings
    from nexo_os.data.ingest import ingest
    from nexo_os.data.snapshot_repository import SnapshotRepository

    s = get_settings()
    snapshot_fecha = s.snapshot_fecha_override or date.today()
    repo = SnapshotRepository.open(s.store_path)
    try:
        result = ingest(
            workbook,
            cargado_por="cli",
            repo=repo,
            snapshot_fecha=snapshot_fecha,
            now=datetime.now(),
        )
    finally:
        repo.close()
    print(result.report.render_es())
    return 0 if result.ok else 1


def _cmd_backup() -> int:
    from nexo_os.config import get_settings
    from nexo_os.data import store

    s = get_settings()
    dest = store.backup(s.store_path, s.backup_dir)
    print(f"Backup escrito en {dest}")
    return 0


def _cmd_restore(file: str) -> int:
    from nexo_os.config import get_settings
    from nexo_os.data import store

    s = get_settings()
    store.restore(file, s.store_path)
    print(f"Store restaurado desde {file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
