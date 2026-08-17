"""Shareable dashboard, hosted on Streamlit Community Cloud. Same backend
(app/agents, app/claude_client, app/run_pipeline, app/db) as the local
FastAPI dashboard in app/main.py — this file only reimplements the UI, so
routing, citation validation, and synthesis behave identically either way.

Secrets (ANTHROPIC_API_KEY, optionally CLAUDE_MODEL) are configured via
Streamlit Cloud's Settings -> Secrets, not committed to the repo.
"""
import asyncio
import json
import os
from pathlib import Path

import streamlit as st

try:
    for _key in ("ANTHROPIC_API_KEY", "CLAUDE_MODEL", "FOREMAN_DB_PATH"):
        if _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
except FileNotFoundError:
    pass  # no .streamlit/secrets.toml locally — local dev uses .env instead

from app.db import get_conn, get_submission, init_db, list_runs, list_submissions, upsert_submission
from app.run_pipeline import run_submission

BASE_DIR = Path(__file__).resolve().parent
SUBMISSIONS_FIXTURE = BASE_DIR / "data" / "submissions" / "submissions.json"

SPECIALIST_LABELS = {
    "coverage_checker": "Coverage Checker",
    "consistency_checker": "Consistency Checker",
    "pricing_checker": "Pricing / Risk Checker",
}
DECISION_COLOR = {"accept": "green", "decline": "red", "refer": "orange"}
SEVERITY_COLOR = {"critical": "red", "high": "orange", "medium": "blue", "low": "gray", "info": "gray"}


@st.cache_resource
def init_data():
    init_db()
    with open(SUBMISSIONS_FIXTURE, encoding="utf-8") as f:
        fixtures = json.load(f)
    with get_conn() as conn:
        for sub in fixtures:
            upsert_submission(conn, sub)
    return True


def badge(text: str, color: str) -> str:
    return f":{color}[**{text}**]"


def load_submissions():
    with get_conn() as conn:
        subs = list_submissions(conn)
        latest_runs = {r["submission_id"]: r for r in list_runs(conn)}
    return [{**sub, "_latest_run": latest_runs.get(sub["submission_id"])} for sub in subs]


def render_specialist_card(v: dict):
    with st.container(border=True):
        st.markdown(
            f"**{SPECIALIST_LABELS.get(v['specialist'], v['specialist'])}** — "
            f"{badge(v['overall_severity'], SEVERITY_COLOR.get(v['overall_severity'], 'gray'))} "
            f"· confidence {v['overall_confidence'] * 100:.0f}%"
        )
        st.write(v["summary"])
        if v["findings"]:
            for f in v["findings"]:
                st.markdown(
                    f"- {badge(f['severity'], SEVERITY_COLOR.get(f['severity'], 'gray'))} "
                    f"(confidence {f['confidence'] * 100:.0f}%) — {f['finding']}"
                )
                st.caption(f"citation: `{f['citation']['field']}` — \"{f['citation']['excerpt']}\"")
        else:
            st.caption("No findings — nothing to flag.")
        if v.get("dropped_findings"):
            st.warning(
                f"{len(v['dropped_findings'])} finding(s) dropped — the model couldn't cite a field "
                "that supported the claim."
            )
        if v.get("tool_calls"):
            with st.expander(f"{len(v['tool_calls'])} reference lookup(s)"):
                for tc in v["tool_calls"]:
                    st.code(f"{tc['tool']}({json.dumps(tc['input'])})\n→ {json.dumps(tc['result'])}")


def render_trace(trace: dict):
    decision = trace["decision"]
    st.markdown(f"## {badge(decision['decision'].upper(), DECISION_COLOR.get(decision['decision'], 'gray'))}")
    st.progress(decision["confidence"], text=f"Combined confidence: {decision['confidence'] * 100:.0f}%")
    st.write(decision["rationale"])

    st.divider()
    st.subheader("Orchestration trace")
    verdicts_by_specialist = {v["specialist"]: v for v in trace["verdicts"]}
    for step in trace["routing"]:
        names = step["specialists_invoked"]
        phase_title = f"Phase {step['phase']} — " + (
            " + ".join(SPECIALIST_LABELS.get(n, n) for n in names) if names else "skipped"
        )
        st.markdown(f"**{phase_title}**")
        st.caption(step["reason"])
        if not names:
            st.info("Pricing check skipped this phase — see reason above.")
        for name in names:
            v = verdicts_by_specialist.get(name)
            if v:
                render_specialist_card(v)

    st.divider()
    with st.expander("How this decision was scored"):
        sb = decision["score_breakdown"]
        rows = [
            {
                "Specialist": SPECIALIST_LABELS.get(e["specialist"], e["specialist"]),
                "Worst finding severity": e["worst_severity"],
                "Confidence": f"{e['worst_confidence'] * 100:.0f}%",
                "Score": e["specialist_score"],
                "Weight in combined confidence": f"{e['confidence_weight']}×",
            }
            for e in sb["per_specialist"]
        ]
        st.table(rows)
        st.caption(
            f"Decline threshold: score ≥ {sb['decline_threshold']:.2f}. "
            f"Refer threshold: score ≥ {sb['refer_threshold']:.2f} or "
            f"{sb['refer_medium_plus_count_trigger']}+ independent medium-or-above findings "
            f"(this run had {sb['medium_plus_finding_count']}). "
            f"Highest specialist score this run: {sb['max_specialist_score']:.2f}."
        )
        st.caption(sb["combined_confidence_formula"])


def main():
    st.set_page_config(page_title="Foreman", page_icon="\U0001F4CB", layout="wide")
    init_data()

    st.sidebar.title("Foreman")
    st.sidebar.caption("Insurance submission review — multi-agent Claude orchestration demo")
    filter_choice = st.sidebar.radio("Filter by latest decision", ["all", "accept", "decline", "refer"], horizontal=True)

    submissions = load_submissions()
    if filter_choice != "all":
        submissions = [
            s for s in submissions
            if s["_latest_run"] and s["_latest_run"]["decision"]["decision"] == filter_choice
        ]

    st.sidebar.divider()

    if not submissions:
        st.sidebar.caption("No submissions match this filter yet — run some first.")
        st.title("Foreman")
        st.info("No submissions match the current filter. Pick \"all\" in the sidebar to see everything.")
        return

    by_id = {s["submission_id"]: s for s in submissions}

    def _option_label(sid: str) -> str:
        s = by_id[sid]
        run = s["_latest_run"]
        label = f"{s['business_name']} ({sid}) — known: {s.get('known_label', '—')}"
        if run:
            label += f" · last run: {run['decision']['decision']}"
        return label

    sub_id = st.sidebar.selectbox(
        "Submission",
        options=list(by_id.keys()),
        format_func=_option_label,
    )
    with get_conn() as conn:
        submission = get_submission(conn, sub_id)
        runs = list_runs(conn, sub_id)
    trace = runs[0] if runs else None

    st.header(submission["business_name"])
    st.caption(
        f"{submission['business_type']} · {submission['industry_class_code']} · "
        f"{submission['location']['city']}, {submission['location']['state']} · "
        f"${submission['annual_revenue']:,} revenue · {submission['employee_count']} employees"
    )

    if st.button("Run live" if not trace else "Run again", type="primary"):
        new_trace = None
        with st.spinner("Running orchestrator — calls Claude 2-3×..."):
            try:
                new_trace = asyncio.run(run_submission(submission, persist=True))
            except Exception as e:
                st.error(f"Run failed: {e}. Check that ANTHROPIC_API_KEY is set correctly in Secrets.")
        if new_trace:
            st.rerun()

    if trace:
        known = submission.get("known_label")
        if known:
            match = known == trace["decision"]["decision"]
            st.info(f"Eval label: **{known}** — {'matches' if match else 'differs from'} orchestrator decision.")
        render_trace(trace)
    else:
        st.info("No run yet for this submission. Click **Run live** to invoke the orchestrator.")


main()
