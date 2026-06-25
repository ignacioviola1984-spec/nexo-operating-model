"""
test_report_metrics.py - Tests for the anonymized metrics report.

Checks: the report is generated from sample run state(s), the rates reconcile with
the counts, the grounding aggregation is right, the per-run history upserts
(no duplicates), and the output contains NO PII (plus the privacy scan itself
catches identifiers and blocks the write). Pure-Python, no API key.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEXO = os.path.dirname(HERE)
sys.path.insert(0, NEXO)

import report_metrics as rm

# PII deliberately embedded in the sample state's actions; it must NEVER reach the output.
PII = {"nombre": "Juan Gomez", "email": "juan.gomez@example.com",
       "telefono": "+54 9 11 1234 5678", "poliza": "AUT-00012"}


def _action(agente, estado, conf, source):
    return {"id": f"{agente}:{estado}:{conf}", "agente": agente, "tipo": "renovacion",
            "cliente_nombre": PII["nombre"], "email": PII["email"],
            "telefono": PII["telefono"], "poliza": PII["poliza"],
            "estado": estado, "confianza": conf,
            "datos": {"_mensaje_source": source}}


def _state(run_started, actions, narrative_source=None):
    agents = {}
    if narrative_source is not None:
        agents["analisis_cartera_agent"] = {"narrative": "insight del panel",
                                            "narrative_source": narrative_source}
    return {"meta": {"started": run_started},
            "inbox": [_action(*a) for a in actions], "agents": agents}


def _gen(tmp_path, state, name="r"):
    return rm.generate(
        state=state, history_path=str(tmp_path / "hist.jsonl"),
        md_path=str(tmp_path / f"{name}.md"), json_path=str(tmp_path / f"{name}.json"),
        audit_path=str(tmp_path / "noaudit.jsonl"))


# -- reconciliation --------------------------------------------------------

def test_rates_reconcile_with_counts(tmp_path):
    state = _state("2026-06-25T10:00:00", [
        ("renovaciones_agent", "aprobada", 0.9, "template"),
        ("renovaciones_agent", "aprobada", 0.8, "template"),
        ("renovaciones_agent", "editada", 0.7, "template"),
        ("renovaciones_agent", "rechazada", 0.6, "template"),
        ("cobranza_agent", "aprobada", 0.95, "template"),
        ("cobranza_agent", "pendiente", 0.5, "template"),
    ], narrative_source="template")
    rep = _gen(tmp_path, state)["report"]

    ren = rep["actions"]["by_agent"]["renovaciones"]
    assert ren["proposed"] == 4
    assert sum(ren["estados"].values()) == ren["proposed"]      # counts partition
    assert ren["rates"]["aprobada"] == 50.0                     # 2/4
    assert ren["rates"]["editada"] == 25.0
    assert ren["rates"]["rechazada"] == 25.0
    # global = sum across action agents
    g = rep["actions"]["global"]
    assert g["proposed"] == 6
    assert sum(g["estados"].values()) == 6
    assert rep["actions"]["total_proposed"] == 6
    # confidence average is computed in code (rounded %), within [0,100]
    assert 0 <= ren["avg_confidence_pct"] <= 100


# -- grounding -------------------------------------------------------------

def test_grounding_aggregation(tmp_path):
    state = _state("2026-06-25T11:00:00", [
        ("renovaciones_agent", "aprobada", 0.9, "llm"),
        ("renovaciones_agent", "aprobada", 0.9, "llm"),
        ("cobranza_agent", "aprobada", 0.9, "template_guarded"),
        ("cobranza_agent", "aprobada", 0.9, "template_error"),
        ("cross_sell_agent", "aprobada", 0.9, "template"),
        ("cross_sell_agent", "aprobada", 0.9, "template"),
    ])
    gr = _gen(tmp_path, state)["report"]["grounding"]
    assert gr["llm_drafts_attempted"] == 4         # llm + guarded + error (not plain template)
    assert gr["passed_guard"] == 2                 # only source == "llm"
    assert gr["fell_to_template"] == 2
    assert gr["grounded_pct"] == 50.0
    assert gr["by_source"]["template"] == 2


def test_grounding_offline_is_na(tmp_path):
    state = _state("2026-06-25T12:00:00",
                   [("renovaciones_agent", "aprobada", 0.9, "template")])
    gr = _gen(tmp_path, state)["report"]["grounding"]
    assert gr["llm_drafts_attempted"] == 0
    assert gr["grounded_pct"] is None              # NA -> rendered as offline


# -- privacy: output has no PII; the scan catches identifiers --------------

def test_output_contains_no_pii(tmp_path):
    state = _state("2026-06-25T13:00:00", [
        ("renovaciones_agent", "aprobada", 0.9, "template"),
        ("cobranza_agent", "rechazada", 0.6, "template"),
    ], narrative_source="template")
    out = _gen(tmp_path, state)
    blob = out["md"] + open(out["json_path"], encoding="utf-8").read()
    for v in PII.values():
        assert v not in blob
    assert "@" not in blob          # no email anywhere
    assert "+54" not in blob


def test_scan_for_pii_detects_each_kind():
    assert rm.scan_for_pii("contactar a Juan Gomez hoy", {"Juan Gomez"})
    assert rm.scan_for_pii("mail a juan@example.com", set())          # email regex
    assert rm.scan_for_pii("poliza AUT-00012 vencida", set())        # poliza regex
    assert rm.scan_for_pii("tel +54 9 11 1234 5678", set())          # phone regex
    # aggregates-only text is clean (no false positive on counts/percentages)
    assert rm.scan_for_pii("22 propuestas, 100.0% aprobadas, conf 84.8%", set()) == []


def test_privacy_error_blocks_write(tmp_path, monkeypatch):
    state = _state("2026-06-25T14:00:00",
                   [("renovaciones_agent", "aprobada", 0.9, "template")])
    # simulate a leak: the renderer emits a client name
    monkeypatch.setattr(rm, "render_md", lambda report: f"Contactar a {PII['nombre']} ya.")
    md_path = str(tmp_path / "leak.md")
    try:
        rm.generate(state=state, history_path=str(tmp_path / "h.jsonl"),
                    md_path=md_path, json_path=str(tmp_path / "leak.json"),
                    audit_path=str(tmp_path / "n.jsonl"))
        assert False, "should have raised PrivacyError"
    except rm.PrivacyError:
        pass
    assert not os.path.exists(md_path)             # nothing written on a leak


# -- history: upsert + cross-run counts ------------------------------------

def test_history_upserts_same_run(tmp_path):
    hp = str(tmp_path / "hist.jsonl")
    rm.record_run(_state("2026-06-25T15:00:00",
                         [("renovaciones_agent", "pendiente", 0.9, "template")]), history_path=hp)
    # same run_started, now decided -> should REPLACE, not duplicate
    rm.record_run(_state("2026-06-25T15:00:00",
                         [("renovaciones_agent", "aprobada", 0.9, "template")]), history_path=hp)
    rows = rm._read_history(hp)
    assert len(rows) == 1
    rep = rm.aggregate(rows)
    assert rep["runs"]["count"] == 1
    assert rep["actions"]["by_agent"]["renovaciones"]["estados"]["aprobada"] == 1


def test_runs_count_and_date_range(tmp_path):
    hp = str(tmp_path / "hist.jsonl")
    rm.record_run(_state("2026-06-24T09:00:00",
                         [("cobranza_agent", "aprobada", 0.9, "template")]), history_path=hp)
    rm.record_run(_state("2026-06-25T09:00:00",
                         [("cobranza_agent", "aprobada", 0.9, "template")]), history_path=hp)
    rep = rm.aggregate(rm._read_history(hp))
    assert rep["runs"]["count"] == 2
    assert rep["runs"]["date_from"] == "2026-06-24T09:00:00"
    assert rep["runs"]["date_to"] == "2026-06-25T09:00:00"
    assert rep["actions"]["by_agent"]["cobranza"]["proposed"] == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
