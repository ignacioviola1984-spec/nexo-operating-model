"""PII minimization helpers (§13).

The model receives only what a message needs: prefer first names / identifiers
over full documents, emails, phones, or birth dates. These helpers are used when
building narrate prompts and are gated by the PII-minimization eval (§16).
"""

from __future__ import annotations


def first_name(nombre: str | None) -> str:
    """First token of a name (e.g. 'Ana Ficticia C01' -> 'Ana')."""
    if not nombre:
        return ""
    return nombre.strip().split()[0]


def mask_document(documento: str | None) -> str:
    """Mask all but the last 2 chars of a document (CUIT/DNI)."""
    if not documento:
        return ""
    d = documento.strip()
    return ("*" * max(0, len(d) - 2)) + d[-2:] if len(d) > 2 else "*" * len(d)


def safe_lead_label(nombre_prospecto: str | None, lead_id: str) -> str:
    """A prospect reference safe for prose: first name + lead id, no full contact."""
    fn = first_name(nombre_prospecto)
    return f"{fn} ({lead_id})" if fn else lead_id
