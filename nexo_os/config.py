"""Central configuration for Nexo v3 (pydantic-settings).

Every tunable lives here and is documented. There are NO magic numbers in agent
or core code: thresholds (mora buckets, SLA windows, conversion floors, priority
cutoffs, stage probabilities, confidence parameters, reconciliation tolerances)
are all defined here. No cloud settings exist, by design.

Secrets and the bootstrap admin come from the repo-root .env (gitignored). The
system runs end to end with only ANTHROPIC_API_KEY (optional, prose only) and the
bootstrap admin set.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


class Thresholds(BaseSettings):
    """Deterministic thresholds for core + agents. Tunable, never hardcoded.

    These are plain defaults (not env-driven) so they live in one documented
    place; override in code/tests by constructing Thresholds(...) when needed.
    """

    # --- Cobranza y morosidad (collections + delinquency) ---
    # Aging buckets in days, by upper bound. "90+" is the implicit open bucket.
    mora_bucket_bounds: tuple[int, int, int] = (30, 60, 90)  # -> 0,1-30,31-60,61-90,90+
    # Days of grace after an installment due date before it counts as overdue.
    mora_grace_days: int = 0

    # --- Renovaciones (renewals) ---
    renewal_windows_days: tuple[int, int, int] = (30, 60, 90)  # expiring-in horizons
    renewal_urgent_days: int = 7  # <= this -> ALTA urgency

    # --- Pipeline comercial (pipeline + conversion) ---
    # Stage probabilities for the weighted forecast (deterministic table).
    stage_probabilities: dict[str, float] = Field(
        default_factory=lambda: {
            "nuevo": 0.10,
            "contactado": 0.25,
            "cotizado": 0.45,
            "presentado": 0.70,
            "ganado": 1.00,
            "perdido": 0.00,
        }
    )
    lead_no_quote_days: int = 14  # lead with no quote past this window -> flag
    quote_not_presented_days: int = 10  # quote issued but never presented past this -> flag
    stage_aging_days: int = 21  # opportunity stuck in a stage longer than this -> flag

    # --- Cartera (portfolio concentration) ---
    # Herfindahl-Hirschman Index over insurer share; above this -> over-concentration.
    hhi_concentration_threshold: float = 0.25
    shrinking_segment_pct: float = -0.10  # segment premium down > 10% vs prior snapshot

    # --- Cobranza (recovery prioritization) ---
    # Client-value multiplier applied to the 'premium' segment in recovery scoring.
    recovery_premium_weight: float = 1.5

    # --- Commission receivable aging ---
    commission_terms_offset_days: int = 30  # settlement expected period-end + this

    # --- Confidence scoring (deterministic; never model-produced) ---
    conf_weight_data: float = 0.40  # weight on data completeness
    conf_weight_signal: float = 0.60  # weight on signal/rule strength

    # --- Priority cutoffs (ARS amount at stake) ---
    priority_alta_ars: Decimal = Decimal("200000")
    priority_media_ars: Decimal = Decimal("50000")
    # Urgency-only branch (when monto_en_juego_ars is null): days threshold.
    priority_urgent_days: int = 7

    # --- Reliability / reconciliation tolerances ---
    # Relative tolerance for cross-agent figure reconciliation (e.g. 0.005 = 0.5%).
    reconciliation_rel_tolerance: float = 0.005
    reconciliation_abs_tolerance_ars: Decimal = Decimal("1.00")

    model_config = SettingsConfigDict(env_prefix="NEXO_THRESH_", extra="ignore")


class Settings(BaseSettings):
    """Runtime configuration. Reads the repo-root .env."""

    # --- Claude (prose layer only) ---
    # Read from the standard ANTHROPIC_API_KEY (no NEXO_ prefix).
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "NEXO_ANTHROPIC_API_KEY"),
    )
    model: str = "claude-opus-4-8"
    use_llm: bool = False

    # --- Bootstrap admin (first-boot only; see `make bootstrap-admin`) ---
    bootstrap_admin_user: str = ""
    bootstrap_admin_name: str = ""
    bootstrap_admin_password: str = ""

    # --- Local store + backups (the system of record; no cloud) ---
    store_path: Path = REPO_ROOT / "nexo_os" / "data" / "store" / "nexo.duckdb"
    backup_dir: Path = REPO_ROOT / "backups"

    # --- Auth ---
    session_ttl_minutes: int = 480

    # --- Snapshot "as of" override (default: the active snapshot's date) ---
    # When unset, the active snapshot's snapshot_fecha is the as-of date.
    snapshot_fecha_override: date | None = None

    thresholds: Thresholds = Field(default_factory=Thresholds)

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        env_prefix="NEXO_",
        extra="ignore",
    )

    @property
    def llm_enabled(self) -> bool:
        """Claude prose is on only when explicitly enabled AND a key is present."""
        return self.use_llm and bool(self.anthropic_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Process-wide singleton (re-read with reload_settings() in tests)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force a fresh read of the environment/.env (used by tests)."""
    global _settings
    _settings = Settings()
    return _settings
