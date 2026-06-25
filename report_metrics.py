"""
report_metrics.py - Deterministic, anonymized metrics report (NO LLM, no API).

Every number here is computed in Python from the run logs. The report is
aggregates only: counts, rates and percentages. It NEVER contains a client name,
email, phone or policy number, and a final privacy scan FAILS the generation if
any such identifier would leak.

Why a history file: audit_log.jsonl and nexo_state.json are reset on every run
(fresh_audit + overwrite), so on their own they only describe the latest run. To
report across runs (run count, date range, grounded %), Nexo accumulates a
PII-FREE per-run summary in outputs/metrics_history.jsonl (the "registro
minimo"). record_run() upserts the current run's summary there; the report
aggregates that history. The message-draft `source` (llm / template /
template_guarded / template_error) is already persisted per action in
state["inbox"][i]["datos"]["_mensaje_source"], so the grounded % is derivable.

  python report_metrics.py        # generate from the current nexo_state.json
"""

import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import paths
from shared_state import now_iso

HISTORY_PATH = os.path.join(paths.OUTPUTS_DIR, "metrics_history.jsonl")
MD_PATH = os.path.join(paths.OUTPUTS_DIR, "metrics_report.md")
JSON_PATH = os.path.join(paths.OUTPUTS_DIR, "metrics_report.json")

# The four action agents (analisis produces a dashboard insight, no per-client action).
ACTION_AGENTS = ["renovaciones_agent", "cobranza_agent", "reactivacion_agent", "cross_sell_agent"]
AGENT_LABEL = {
    "renovaciones_agent": "renovaciones", "cobranza_agent": "cobranza",
    "reactivacion_agent": "reactivacion", "cross_sell_agent": "cross_sell",
    "analisis_cartera_agent": "analisis",
}
ESTADOS = ["pendiente", "aprobada", "editada", "rechazada"]
# A draft whose source is one of these means LLM mode was actually attempted.
LLM_SOURCES = ("llm", "template_guarded", "template_error")


class PrivacyError(Exception):
    """Raised when the report output would contain a cartera identifier."""


# --------------------------------------------------------------------------
# Per-run PII-free summary + the accumulating history.
# --------------------------------------------------------------------------

def _blank_agent():
    return {"proposed": 0, "estados": {e: 0 for e in ESTADOS},
            "sources": {}, "conf_sum": 0.0, "conf_n": 0}


def summarize_run(state) -> dict:
    """Reduce one run's state to a PII-FREE per-agent summary (counts only)."""
    by_agent = {}
    for d in state.get("inbox", []):
        ag = d.get("agente", "desconocido")
        a = by_agent.setdefault(ag, _blank_agent())
        a["proposed"] += 1
        a["estados"][d.get("estado", "pendiente")] = \
            a["estados"].get(d.get("estado", "pendiente"), 0) + 1
        src = (d.get("datos") or {}).get("_mensaje_source", "template")
        a["sources"][src] = a["sources"].get(src, 0) + 1
        conf = d.get("confianza")
        if isinstance(conf, (int, float)):
            a["conf_sum"] += float(conf)
            a["conf_n"] += 1
    ana = state.get("agents", {}).get("analisis_cartera_agent", {})
    return {
        "run_started": state.get("meta", {}).get("started"),
        "recorded_at": now_iso(),
        "by_agent": by_agent,
        "analisis": {"has_narrative": bool(ana.get("narrative")),
                     "narrative_source": ana.get("narrative_source")},
    }


def _read_history(history_path=None):
    history_path = history_path or HISTORY_PATH
    if not os.path.exists(history_path):
        return []
    out = []
    with open(history_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def record_run(state, history_path=None):
    """Upsert this run's PII-free summary into the history (keyed by run_started),
    so re-recording the same run updates it instead of duplicating it."""
    history_path = history_path or HISTORY_PATH
    paths.ensure_dirs()
    summary = summarize_run(state)
    rid = summary["run_started"]
    rows = [r for r in _read_history(history_path) if r.get("run_started") != rid]
    rows.append(summary)
    with open(history_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return summary


# --------------------------------------------------------------------------
# Aggregation across runs.
# --------------------------------------------------------------------------

def _pct(n, d):
    return round(n / d * 100, 1) if d else None


def aggregate(history, audit_events=None):
    """Build the anonymized report dict from the per-run history."""
    runs = [r for r in history if r.get("run_started")]
    started = sorted(r["run_started"] for r in runs)

    totals = {}
    for r in runs:
        for ag, a in r.get("by_agent", {}).items():
            t = totals.setdefault(ag, _blank_agent())
            t["proposed"] += a.get("proposed", 0)
            for e, c in a.get("estados", {}).items():
                t["estados"][e] = t["estados"].get(e, 0) + c
            for s, c in a.get("sources", {}).items():
                t["sources"][s] = t["sources"].get(s, 0) + c
            t["conf_sum"] += a.get("conf_sum", 0.0)
            t["conf_n"] += a.get("conf_n", 0)

    # analisis narratives + their sources
    ana_sources, ana_narratives = {}, 0
    for r in runs:
        ana = r.get("analisis", {})
        if ana.get("has_narrative"):
            ana_narratives += 1
            s = ana.get("narrative_source") or "template"
            ana_sources[s] = ana_sources.get(s, 0) + 1

    def agent_row(t):
        prop = t["proposed"]
        est = t["estados"]
        return {
            "proposed": prop,
            "estados": est,
            "rates": {e: _pct(est.get(e, 0), prop) for e in ESTADOS},
            "avg_confidence_pct": round(t["conf_sum"] / t["conf_n"] * 100, 1) if t["conf_n"] else None,
        }

    by_agent = {}
    gprop = 0
    gest = {e: 0 for e in ESTADOS}
    gconf_sum = gconf_n = 0
    for ag in ACTION_AGENTS:
        t = totals.get(ag, _blank_agent())
        by_agent[AGENT_LABEL[ag]] = agent_row(t)
        gprop += t["proposed"]
        for e in ESTADOS:
            gest[e] += t["estados"].get(e, 0)
        gconf_sum += t["conf_sum"]
        gconf_n += t["conf_n"]

    by_agent["analisis"] = {
        "proposed": 0, "narratives": ana_narratives, "sources": ana_sources,
        "note": "insight del panel, sin acciones por cliente",
    }

    global_row = {
        "proposed": gprop, "estados": gest,
        "rates": {e: _pct(gest[e], gprop) for e in ESTADOS},
        "avg_confidence_pct": round(gconf_sum / gconf_n * 100, 1) if gconf_n else None,
    }

    # grounding: merge sources of the 4 action agents + analisis narratives
    merged_sources = defaultdict(int)
    for ag in ACTION_AGENTS:
        for s, c in totals.get(ag, _blank_agent())["sources"].items():
            merged_sources[s] += c
    for s, c in ana_sources.items():
        merged_sources[s] += c
    llm_attempted = sum(c for s, c in merged_sources.items() if s in LLM_SOURCES)
    passed = merged_sources.get("llm", 0)

    report = {
        "scope": "Agregado anonimo de las corridas registradas (solo conteos y %).",
        "generated_at": now_iso(),
        "runs": {
            "count": len(runs),
            "date_from": started[0] if started else None,
            "date_to": started[-1] if started else None,
        },
        "actions": {"total_proposed": gprop, "by_agent": by_agent, "global": global_row},
        "grounding": {
            "llm_drafts_attempted": llm_attempted,
            "passed_guard": passed,
            "fell_to_template": llm_attempted - passed,
            "grounded_pct": _pct(passed, llm_attempted),
            "by_source": dict(sorted(merged_sources.items())),
        },
    }
    if audit_events is not None:
        ts = sorted(e.get("ts") for e in audit_events if e.get("ts"))
        report["last_run_audit"] = {
            "events": len(audit_events),
            "from": ts[0] if ts else None,
            "to": ts[-1] if ts else None,
        }
    return report


# --------------------------------------------------------------------------
# Rendering.
# --------------------------------------------------------------------------

def _f(x, suffix="%"):
    return "s/d" if x is None else f"{x}{suffix}"


def render_md(report) -> str:
    r = report
    L = ["# Reporte de métricas de Nexo (anónimo)", ""]
    L.append("> Este reporte no contiene datos de clientes, solo conteos y porcentajes.")
    L.append("")
    L.append("## Actividad")
    L.append(f"- Corridas registradas: **{r['runs']['count']}**")
    L.append(f"- Período: {r['runs']['date_from'] or 's/d'} a {r['runs']['date_to'] or 's/d'}")
    if "last_run_audit" in r:
        a = r["last_run_audit"]
        L.append(f"- Última corrida (auditoría): {a['events']} eventos, "
                 f"de {a['from'] or 's/d'} a {a['to'] or 's/d'}")
    L.append("")
    L.append("## Acciones propuestas")
    L.append(f"- Total: **{r['actions']['total_proposed']}**")
    L.append("")
    L.append("| Agente | Propuestas | Aprob. | Edit. | Rech. | Pend. | % aprob. | % edit. | % rech. | Conf. prom. |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for label in ["renovaciones", "cobranza", "reactivacion", "cross_sell"]:
        a = r["actions"]["by_agent"][label]
        e = a["estados"]
        rt = a["rates"]
        L.append(f"| {label} | {a['proposed']} | {e['aprobada']} | {e['editada']} | "
                 f"{e['rechazada']} | {e['pendiente']} | {_f(rt['aprobada'])} | "
                 f"{_f(rt['editada'])} | {_f(rt['rechazada'])} | {_f(a['avg_confidence_pct'])} |")
    ana = r["actions"]["by_agent"]["analisis"]
    L.append(f"| analisis | 0 (insight) | — | — | — | — | — | — | — | — |")
    g = r["actions"]["global"]
    ge = g["estados"]
    gr = g["rates"]
    L.append("")
    L.append(f"**Global:** {g['proposed']} propuestas · aprobadas {ge['aprobada']} ({_f(gr['aprobada'])}) · "
             f"editadas {ge['editada']} ({_f(gr['editada'])}) · rechazadas {ge['rechazada']} ({_f(gr['rechazada'])}) · "
             f"pendientes {ge['pendiente']} · confianza promedio {_f(g['avg_confidence_pct'])}.")
    L.append(f"- Insights del panel generados: {ana['narratives']}")
    L.append("")
    gr2 = r["grounding"]
    L.append("## Grounding (modo IA)")
    if gr2["llm_drafts_attempted"]:
        L.append(f"- Borradores con IA (LLM): {gr2['llm_drafts_attempted']}")
        L.append(f"- Pasaron el guard (sin cifras inventadas): {gr2['passed_guard']} "
                 f"(**{_f(gr2['grounded_pct'])}**)")
        L.append(f"- Cayeron a plantilla (guard rechazó o error de API): {gr2['fell_to_template']}")
    else:
        L.append("- No hubo borradores en modo IA: las corridas fueron offline (plantillas determinísticas).")
    L.append("")
    L.append(f"_Generado: {r['generated_at']}._")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# Privacy scan.
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.\w+")
POLIZA_RE = re.compile(r"\b[A-Z]{3}-\d{5}\b")
PHONE_RE = re.compile(r"\+54[\d ]{6,}")


def collect_identifiers(state) -> set:
    """The cartera identifiers present in this run's state (what must NOT leak)."""
    ids = set()
    for d in (state or {}).get("inbox", []):
        for k in ("cliente_nombre", "email", "telefono", "poliza"):
            v = d.get(k)
            if v:
                ids.add(str(v))
    return {i for i in ids if i and len(i) >= 3}


def scan_for_pii(text, identifiers=()):
    """Return a list of PII findings in `text` (exact identifiers + generic
    patterns). Empty list = clean."""
    findings = []
    for ident in identifiers:
        if ident and ident in text:
            findings.append(f"identificador:{ident}")
    for rx, label in ((EMAIL_RE, "email"), (POLIZA_RE, "poliza"), (PHONE_RE, "telefono")):
        m = rx.search(text)
        if m:
            findings.append(f"{label}:{m.group(0)}")
    return findings


# --------------------------------------------------------------------------
# Top-level: generate the report (records the run, aggregates, scans, writes).
# --------------------------------------------------------------------------

def _load_state(state_path=None):
    p = state_path or paths.STATE_PATH
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _load_audit(audit_path=None):
    p = audit_path or paths.AUDIT_PATH
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def generate(state=None, *, record=True, history_path=None, md_path=None,
             json_path=None, state_path=None, audit_path=None):
    """Generate the anonymized report. Records the current run (if any) into the
    history, aggregates the whole history, scans for PII, and writes the .md/.json.
    Raises PrivacyError (without writing) if any identifier would leak."""
    if state is None:
        state = _load_state(state_path)
    if record and state:
        record_run(state, history_path)

    history = _read_history(history_path)
    audit = _load_audit(audit_path)
    report = aggregate(history, audit_events=audit)

    md = render_md(report)
    js = json.dumps(report, ensure_ascii=False, indent=2)

    identifiers = collect_identifiers(state)
    findings = scan_for_pii(md, identifiers) + scan_for_pii(js, identifiers)
    if findings:
        raise PrivacyError(f"el reporte contendría PII y no se escribió: {findings[:5]}")

    paths.ensure_dirs()
    md_path = md_path or MD_PATH
    json_path = json_path or JSON_PATH
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(js)
    return {"report": report, "md": md, "md_path": md_path, "json_path": json_path}


if __name__ == "__main__":
    out = generate()
    print("Reporte escrito en:")
    print(" ", out["md_path"])
    print(" ", out["json_path"])
    print()
    print(out["md"])
