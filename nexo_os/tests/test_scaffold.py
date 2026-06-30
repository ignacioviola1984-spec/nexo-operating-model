"""Phase 0 scaffold smoke tests: the package imports and config/CLI are wired."""

from __future__ import annotations

from decimal import Decimal

from nexo_os import __version__
from nexo_os.cli import build_parser
from nexo_os.config import Settings, Thresholds, reload_settings
from nexo_os.logging import configure_logging, get_logger


def test_version_is_v3():
    assert __version__.startswith("3.")


def test_settings_load_without_env(monkeypatch):
    # The system must construct config with no secrets set (offline default).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEXO_USE_LLM", raising=False)
    s = reload_settings()
    assert isinstance(s, Settings)
    assert s.use_llm is False
    assert s.llm_enabled is False  # no key + not enabled


def test_thresholds_are_centralized_and_typed():
    t = Thresholds()
    assert t.mora_bucket_bounds == (30, 60, 90)
    assert isinstance(t.priority_alta_ars, Decimal)
    assert 0.0 < t.conf_weight_data < 1.0
    assert abs(t.conf_weight_data + t.conf_weight_signal - 1.0) < 1e-9
    assert set(t.stage_probabilities) >= {"nuevo", "cotizado", "ganado", "perdido"}


def test_cli_parser_has_all_subcommands():
    parser = build_parser()
    # Parse each scaffolded subcommand without error.
    for cmd in ["template", "seed", "bootstrap-admin", "run", "eval"]:
        ns = parser.parse_args([cmd])
        assert ns.command == cmd
    ns = parser.parse_args(["ingest", "wb.xlsx"])
    assert ns.command == "ingest" and ns.workbook == "wb.xlsx"


def test_logging_configures():
    configure_logging()
    log = get_logger("test")
    log.info("scaffold_ok", phase=0)  # must not raise
