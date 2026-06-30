"""The prose layer + numeric grounding guard - the only place the model is used.

The model writes Spanish prose given numbers the deterministic core already
computed; it never produces, alters, derives, or rounds a figure. Every number in
the model's output must match a value present in the action's rationale exactly -
otherwise the guard rejects the text and the deterministic template is used
(never ungrounded prose). This is the hard wall for non-negotiable #1.

Offline by default (NEXO_USE_LLM=0): deterministic templates, free and
reproducible, no API key. With NEXO_USE_LLM=1 + a key, Claude drafts and the
guard still gates every figure.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal

from nexo_os.config import Settings, get_settings

_NUM_TOKEN = re.compile(r"\d[\d.,]*")


def _digits(token: str) -> str:
    """Canonical key: digits only (drop thousands/decimal separators)."""
    return "".join(ch for ch in token if ch.isdigit())


def numbers_in(text: str) -> set[str]:
    """Set of canonical digit-keys for every numeric token in `text`."""
    out = set()
    for m in _NUM_TOKEN.findall(text):
        d = _digits(m)
        if d:
            out.add(d)
    return out


def allowed_forms(value: object) -> set[str]:
    """Canonical digit-keys a single allowed value may legitimately appear as."""
    forms: set[str] = set()
    if value is None:
        return forms
    candidates = [str(value)]
    if isinstance(value, Decimal | float | int):
        try:
            candidates.append(str(int(value)))  # integer-pesos form (drops .00)
        except (ValueError, OverflowError):
            pass
        if isinstance(value, Decimal | float):
            # percentage form: 0.10 -> "10" (when an agent shows a rate as %)
            pct = Decimal(str(value)) * 100
            candidates.append(str(int(pct)))
            candidates.append(str(pct))
    for c in candidates:
        d = _digits(c)
        if d:
            forms.add(d)
    return forms


def build_allowed(values: Iterable[object]) -> set[str]:
    allowed: set[str] = set()
    for v in values:
        allowed |= allowed_forms(v)
    return allowed


def extract_numbers(obj: object) -> list[object]:
    """Recursively pull numeric leaves from a rationale dict/list (for the
    allowed set). Strings that parse as numbers are included."""
    out: list[object] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list | tuple):
            for v in o:
                walk(v)
        elif isinstance(o, bool):
            return
        elif isinstance(o, int | float | Decimal):
            out.append(o)
        elif isinstance(o, str):
            if _NUM_TOKEN.fullmatch(o.strip()):
                out.append(o.strip())

    walk(obj)
    return out


def grounding_ok(text: str, allowed_values: Iterable[object]) -> tuple[bool, list[str]]:
    """(ok, offending): ok is False if `text` cites a number not derivable from
    `allowed_values`. No rounding, no derived arithmetic, no approximations."""
    allowed = build_allowed(allowed_values)
    offending = sorted(n for n in numbers_in(text) if n not in allowed)
    return (not offending), offending


def draft(
    *,
    system: str,
    prompt: str,
    allowed_values: Iterable[object],
    fallback: str,
    settings: Settings | None = None,
    max_tokens: int = 400,
) -> dict[str, str]:
    """Return {'text', 'source'}. Uses Claude only when enabled; always gates the
    output through the grounding guard and falls back to the deterministic
    template on disabled/error/ungrounded."""
    settings = settings or get_settings()
    allowed = list(allowed_values)

    if not settings.llm_enabled:
        return {"text": fallback, "source": "template"}

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text").strip()
    except Exception:
        return {"text": fallback, "source": "template_error"}

    ok, _offending = grounding_ok(text, allowed)
    if not text or not ok:
        return {"text": fallback, "source": "template_guarded"}
    return {"text": text, "source": "llm"}
