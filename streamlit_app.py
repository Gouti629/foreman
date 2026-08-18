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

from app.db import (
    get_conn, get_submission, init_db, list_runs, list_submissions, save_run, upsert_submission,
)
from app.run_pipeline import run_submission

BASE_DIR = Path(__file__).resolve().parent
SUBMISSIONS_FIXTURE = BASE_DIR / "data" / "submissions" / "submissions.json"
SEED_RUNS_FIXTURE = BASE_DIR / "data" / "runs" / "seed_runs.json"

SPECIALIST_LABELS = {
    "coverage_checker": "Coverage Checker",
    "consistency_checker": "Consistency Checker",
    "pricing_checker": "Pricing / Risk Checker",
}
DECISION_COLOR = {"accept": "green", "decline": "red", "refer": "orange"}
SEVERITY_COLOR = {"critical": "red", "high": "orange", "medium": "blue", "low": "gray", "info": "gray"}

# Matches the color/typography of the original static dashboard (dashboard/styles.css):
# warm off-white background, white panels, deep green accent, serif headings. Targets real
# HTML tags and Streamlit's documented data-testid attributes, not internal emotion-cache
# class names, so it doesn't depend on Streamlit's unstable internal DOM structure.
_CUSTOM_CSS = """
<style>
h1, h2, h3 {
    font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
}
[data-testid="stSidebar"] {
    border-right: 1px solid #e4e1d8;
}
/* Trim the large default top/bottom margins around the main content area.
   Both selectors target the same element across different Streamlit
   versions/builds — harmless if only one actually matches. */
div[class^='block-container'], .stMainBlockContainer {
    padding-top: 3.6rem;
    padding-bottom: 3.6rem;
}
/* Wider sidebar (default is ~336px). Width is set on the OUTER sidebar
   element (not just its inner div) with !important — Streamlit's own
   resize-state can set an inline width on the outer element, which wins
   over an external stylesheet rule that only targets the inner div,
   leaving the two out of sync and the inner content overlapping the main
   area. min/max-width pins it so that mismatch can't recur (trade-off:
   the sidebar's native drag-to-resize no longer works). Both
   expanded/collapsed rules are needed — collapsing is a negative margin
   equal to the width, so only setting the expanded width leaves a gap. */
[data-testid="stSidebar"][aria-expanded="true"] {
    width: 380px !important;
    min-width: 380px !important;
    max-width: 380px !important;
}
[data-testid="stSidebar"][aria-expanded="true"] > div:first-child {
    width: 380px !important;
}
[data-testid="stSidebar"][aria-expanded="false"] > div:first-child {
    margin-left: -380px !important;
}
</style>
"""

_ROW_DIVIDER = '<hr style="margin:6px 0;border:none;border-top:1px solid rgba(0,0,0,0.08);">'


@st.cache_resource
def init_data():
    init_db()
    with open(SUBMISSIONS_FIXTURE, encoding="utf-8") as f:
        fixtures = json.load(f)
    with get_conn() as conn:
        for sub in fixtures:
            upsert_submission(conn, sub)
    if SEED_RUNS_FIXTURE.exists():
        with open(SEED_RUNS_FIXTURE, encoding="utf-8") as f:
            seed_runs = json.load(f)
        with get_conn() as conn:
            for run in seed_runs:
                save_run(conn, run)
    return True


def badge(text: str, color: str) -> str:
    return f":{color}[**{text}**]"


def esc(text) -> str:
    """Escape markdown-special characters in data/LLM-derived text before it's
    interpolated into a markdown string. Without this, e.g. a finding like
    "premium of $13,500 falls within range ($9,000-$15,500)" gets silently
    mangled — Streamlit's markdown renderer treats text between two `$` as
    LaTeX math. Mirrors the escapeHtml() the original static dashboard used
    for the same reason: never let data render as markup."""
    text = str(text)
    for ch in ("\\", "$", "*", "_", "`", "#"):
        text = text.replace(ch, "\\" + ch)
    return text


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
        st.markdown(esc(v["summary"]))
        if v["findings"]:
            for f in v["findings"]:
                st.markdown(
                    f"- {badge(f['severity'], SEVERITY_COLOR.get(f['severity'], 'gray'))} "
                    f"(confidence {f['confidence'] * 100:.0f}%) — {esc(f['finding'])}"
                )
                st.caption(f"citation: `{esc(f['citation']['field'])}` — \"{esc(f['citation']['excerpt'])}\"")
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
    st.markdown(esc(decision["rationale"]))

    st.divider()
    st.subheader("Orchestration trace")
    verdicts_by_specialist = {v["specialist"]: v for v in trace["verdicts"]}
    for step in trace["routing"]:
        names = step["specialists_invoked"]
        phase_title = f"Phase {step['phase']} — " + (
            " + ".join(SPECIALIST_LABELS.get(n, n) for n in names) if names else "skipped"
        )
        st.markdown(f"**{phase_title}**")
        st.caption(esc(step["reason"]))
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
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
    init_data()

    # gap=None packs title/caption/filter tightly — this top section doesn't need the
    # generous default spacing the case list below benefits from.
    with st.sidebar.container(gap=None):
        st.markdown("### Foreman")
        st.caption("Insurance submission review — multi-agent Claude orchestration demo")
        filter_choice = st.pills(
            "Filter by latest decision",
            ["all", "accept", "decline", "refer"],
            default="all",
            label_visibility="collapsed",
        )
    # st.pills allows deselecting the active pill (returns None) — treat that the
    # same as "all" rather than matching decision == None and hiding everything.
    filter_choice = filter_choice or "all"

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

    # Filtering can exclude whatever was previously selected — always fall back to the
    # first visible submission rather than leaving the main panel with a stale/invalid
    # selection (or, on first load, no selection at all).
    visible_ids = [s["submission_id"] for s in submissions]
    if st.session_state.get("selected_id") not in visible_ids:
        st.session_state.selected_id = visible_ids[0]

    def _select(sid: str):
        # Runs before the rerun triggered by the click, so is_selected below
        # already reflects the new selection on the very same render pass —
        # unlike updating session_state inside an `if button:` block, which
        # lags one run behind (the just-clicked row would render unselected).
        st.session_state.selected_id = sid

    for sub in submissions:
        run = sub["_latest_run"]
        decision = run["decision"]["decision"] if run else None
        is_selected = sub["submission_id"] == st.session_state.selected_id
        st.sidebar.button(
            esc(sub["business_name"]),
            key=f"sel_{sub['submission_id']}",
            use_container_width=True,
            type="primary" if is_selected else "secondary",
            on_click=_select,
            args=(sub["submission_id"],),
        )
        caption = f"{sub['submission_id']} · known: {sub.get('known_label', '—')}"
        if decision:
            caption += f" · last run: {decision}"
        st.sidebar.caption(caption)
        st.sidebar.markdown(_ROW_DIVIDER, unsafe_allow_html=True)

    sub_id = st.session_state.selected_id
    with get_conn() as conn:
        submission = get_submission(conn, sub_id)
        runs = list_runs(conn, sub_id)
    trace = runs[0] if runs else None

    # gap="small" (vs. the unwrapped page's larger default) tightens the space between
    # the header/caption/button/decision-panel/trace blocks below.
    with st.container(gap="small"):
        st.header(esc(submission["business_name"]))
        st.caption(
            f"{esc(submission['business_type'])} · {esc(submission['industry_class_code'])} · "
            f"{esc(submission['location']['city'])}, {esc(submission['location']['state'])} · "
            f"${submission['annual_revenue']:,} revenue · {submission['employee_count']} employees"
        )

        if st.button("Run live" if not trace else "Run again", type="primary"):
            new_trace = None
            with st.spinner("Running orchestrator — calls Claude 2-3×..."):
                try:
                    new_trace = asyncio.run(run_submission(submission, persist=True))
                except Exception as e:
                    st.error(f"Run failed: {esc(e)}. Check that ANTHROPIC_API_KEY is set correctly in Secrets.")
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
