"""Runs every fixture in data/submissions/submissions.json through the real
pipeline (live Claude calls), scores decision accuracy against known_label,
and writes a routing-efficiency + accuracy report to eval/eval_report.md.

Usage (from repo root, with ANTHROPIC_API_KEY set):
    python -m eval.run_eval
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db  # noqa: E402
from app.run_pipeline import run_submission  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBMISSIONS_PATH = os.path.join(BASE_DIR, "data", "submissions", "submissions.json")
REPORT_PATH = os.path.join(BASE_DIR, "eval", "eval_report.md")

DECISIONS = ["accept", "refer", "decline"]


def pricing_skipped(trace: dict) -> bool:
    phase2 = next((s for s in trace["routing"] if s["phase"] == 2), None)
    return bool(phase2) and not phase2["specialists_invoked"]


def phase2_reason(trace: dict) -> str:
    phase2 = next((s for s in trace["routing"] if s["phase"] == 2), None)
    return phase2["reason"] if phase2 else ""


async def _run_with_retries(sub: dict, attempts: int = 3, delay_seconds: int = 5):
    for attempt in range(1, attempts + 1):
        try:
            return await run_submission(sub, persist=True)
        except Exception as e:
            print(f"  attempt {attempt}/{attempts} failed: {e}")
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)
    return None


async def main():
    init_db()
    with open(SUBMISSIONS_PATH, encoding="utf-8") as f:
        submissions = json.load(f)

    results = []
    failed = []
    for sub in submissions:
        print(f"Running {sub['submission_id']} ({sub['business_name']})...")
        trace = await _run_with_retries(sub)
        if trace is None:
            failed.append(sub["submission_id"])
            continue
        results.append((sub, trace))

    if failed:
        print(f"\nFailed after retries (network issue?): {', '.join(failed)}")
        print("Re-run `python -m eval.run_eval` to retry — already-succeeded runs are unaffected (persisted).")

    write_report(results)
    print(f"\nWrote {REPORT_PATH}")


def write_report(results):
    total = len(results)
    correct = sum(1 for sub, trace in results if trace["decision"]["decision"] == sub["known_label"])
    accuracy = correct / total if total else 0.0

    confusion = {actual: {pred: 0 for pred in DECISIONS} for actual in DECISIONS}
    for sub, trace in results:
        actual = sub["known_label"]
        pred = trace["decision"]["decision"]
        if actual in confusion and pred in confusion[actual]:
            confusion[actual][pred] += 1

    skipped = [(s, t) for s, t in results if pricing_skipped(t)]
    ran = [(s, t) for s, t in results if not pricing_skipped(t)]
    skipped_and_declined = [(s, t) for s, t in skipped if t["decision"]["decision"] == "decline"]
    skipped_but_not_declined = [(s, t) for s, t in skipped if t["decision"]["decision"] != "decline"]

    lines = []
    lines.append("# Foreman — Evaluation Summary\n")
    lines.append(f"Generated {datetime.now(timezone.utc).isoformat()} against {total} fixture submissions "
                  f"in `data/submissions/submissions.json`, using live Claude calls.\n")

    lines.append("## Decision accuracy\n")
    lines.append(f"**{correct}/{total} correct ({accuracy:.0%})** — predicted decision matches each "
                  "fixture's `known_label`.\n")

    lines.append("### Confusion matrix (rows = known label, columns = predicted)\n")
    header = "| known \\ predicted | " + " | ".join(DECISIONS) + " |"
    sep = "|---" * (len(DECISIONS) + 1) + "|"
    lines.append(header)
    lines.append(sep)
    for actual in DECISIONS:
        row = [str(confusion[actual][pred]) for pred in DECISIONS]
        lines.append(f"| **{actual}** | " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## Routing efficiency\n")
    lines.append(f"- Pricing check **skipped** in {len(skipped)}/{total} cases "
                  f"(coverage or consistency hard-fail found first).")
    lines.append(f"  - Of those, {len(skipped_and_declined)} ended in **decline** — the skip didn't cost "
                  "anything, the case was decisive without pricing input.")
    if skipped_but_not_declined:
        lines.append(f"  - {len(skipped_but_not_declined)} ended in a decision other than decline despite "
                      "skipping pricing — worth a look at whether the skip was premature: "
                      + ", ".join(f"{s['submission_id']} ({t['decision']['decision']})"
                                  for s, t in skipped_but_not_declined))
    lines.append(f"- Pricing check **ran** in {len(ran)}/{total} cases.\n")

    lines.append("### Per-submission detail\n")
    lines.append("| ID | Business | Known | Predicted | Correct | Pricing | Phase 2 reason |")
    lines.append("|---|---|---|---|---|---|---|")
    for sub, trace in results:
        actual = sub["known_label"]
        pred = trace["decision"]["decision"]
        ok = "✅" if actual == pred else "❌"
        pricing_status = "skipped" if pricing_skipped(trace) else "ran"
        reason = phase2_reason(trace).replace("|", "\\|")
        lines.append(
            f"| {sub['submission_id']} | {sub['business_name']} | {actual} | {pred} | {ok} | "
            f"{pricing_status} | {reason[:140]}{'…' if len(reason) > 140 else ''} |"
        )
    lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
