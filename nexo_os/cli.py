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
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    # Subcommands are dispatched here as their phases land.
    handlers: dict[str, str] = {}
    handler_module = handlers.get(args.command)
    if handler_module is None:
        print(
            f"nexo: command '{args.command}' is scaffolded but not yet wired in this phase.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
