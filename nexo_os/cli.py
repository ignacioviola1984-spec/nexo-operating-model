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
