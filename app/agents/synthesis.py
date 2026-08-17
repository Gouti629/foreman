"""Synthesis: combine whichever specialist verdicts ran into one decision.

Deliberately deterministic (no LLM call here) so the decision and the
confidence score shown on the dashboard are always reproducible from the
verdicts underneath them, and can be unit-tested without hitting the API.
The rationale sentence is built from a template over the actual driving
finding(s) — never freehand text from a model — so it can't say something
the verdicts don't support.
"""
from typing import List

from app.config import SEVERITY_WEIGHT

DECLINE_THRESHOLD = SEVERITY_WEIGHT["critical"] * 0.7  # 2.8: a critical finding, high confidence
REFER_THRESHOLD = SEVERITY_WEIGHT["high"] * 0.5  # 1.5: a high finding, moderate confidence
REFER_MEDIUM_COUNT = 2  # or 2+ independent medium-or-above findings


def _worst_finding(verdict: dict):
    findings = verdict.get("findings", [])
    if not findings:
        return {
            "finding": verdict.get("summary", "No specific finding."),
            "severity": verdict.get("overall_severity", "info"),
            "confidence": verdict.get("overall_confidence", 0.0),
        }
    return max(findings, key=lambda f: (SEVERITY_WEIGHT.get(f["severity"], 0), f["confidence"]))


def synthesize(verdicts: List[dict]) -> dict:
    per_specialist = []
    for v in verdicts:
        wf = _worst_finding(v)
        score = SEVERITY_WEIGHT.get(wf["severity"], 0) * wf["confidence"]
        weight = SEVERITY_WEIGHT.get(wf["severity"], 0) + 1
        per_specialist.append({
            "specialist": v["specialist"],
            "worst_finding": wf["finding"],
            "worst_severity": wf["severity"],
            "worst_confidence": wf["confidence"],
            "specialist_score": round(score, 3),
            "confidence_weight": weight,
            "overall_confidence": v.get("overall_confidence", 0.0),
        })

    medium_plus_count = sum(
        1 for v in verdicts for f in v.get("findings", [])
        if SEVERITY_WEIGHT.get(f["severity"], 0) >= SEVERITY_WEIGHT["medium"]
    )

    max_entry = max(per_specialist, key=lambda e: e["specialist_score"], default=None)
    max_score = max_entry["specialist_score"] if max_entry else 0.0

    weight_sum = sum(e["confidence_weight"] for e in per_specialist)
    combined_confidence = (
        sum(e["overall_confidence"] * e["confidence_weight"] for e in per_specialist) / weight_sum
        if weight_sum else 0.0
    )

    if max_score >= DECLINE_THRESHOLD:
        decision = "decline"
    elif max_score >= REFER_THRESHOLD or medium_plus_count >= REFER_MEDIUM_COUNT:
        decision = "refer"
    else:
        decision = "accept"

    rationale = _build_rationale(decision, per_specialist, max_entry, medium_plus_count, combined_confidence)

    return {
        "decision": decision,
        "confidence": round(combined_confidence, 3),
        "rationale": rationale,
        "score_breakdown": {
            "per_specialist": per_specialist,
            "max_specialist_score": round(max_score, 3),
            "decline_threshold": DECLINE_THRESHOLD,
            "refer_threshold": REFER_THRESHOLD,
            "refer_medium_plus_count_trigger": REFER_MEDIUM_COUNT,
            "medium_plus_finding_count": medium_plus_count,
            "combined_confidence_formula": (
                "weighted average of each specialist's overall_confidence, weighted by "
                "(severity_weight of its worst finding + 1) — specialists with more severe "
                "findings count for more, so a confident critical finding dominates a "
                "confident but unremarkable one."
            ),
        },
    }


def _build_rationale(decision, per_specialist, max_entry, medium_plus_count, combined_confidence) -> str:
    n = len(per_specialist)
    if decision == "decline":
        return (
            f"Declined: {max_entry['specialist']} raised a {max_entry['worst_severity']} finding "
            f"(confidence {max_entry['worst_confidence']:.2f}) — \"{max_entry['worst_finding']}\". "
            f"Combined confidence {combined_confidence:.2f} across {n} specialist(s)."
        )
    if decision == "refer":
        if max_entry and max_entry["specialist_score"] >= REFER_THRESHOLD:
            driver = (
                f"{max_entry['specialist']} raised a {max_entry['worst_severity']} finding "
                f"(confidence {max_entry['worst_confidence']:.2f}) — \"{max_entry['worst_finding']}\""
            )
        else:
            driver = f"{medium_plus_count} independent medium-or-above findings across specialists"
        return (
            f"Referred to underwriter: {driver}. Not clear-cut enough to auto-decide; "
            f"combined confidence {combined_confidence:.2f} across {n} specialist(s)."
        )
    return (
        f"Accepted: no specialist raised a finding at or above the refer threshold "
        f"({REFER_THRESHOLD}) across {n} specialist(s) reviewed. Combined confidence "
        f"{combined_confidence:.2f}."
    )
