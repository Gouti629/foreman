"""Orchestrator: deterministic routing logic over the three specialists.

Routing is implemented as plain, testable code rather than a fourth LLM call
that decides "who to invoke." That's a deliberate choice (see README, "why
this design"): the one part of this system that must be reliable and cheap
to audit is *which specialists ran and why*, so it's driven by the actual
severity/confidence the first-wave specialists returned, not by an LLM's
guess about what it will find before it has looked.

Phase 1 (always runs, in parallel): coverage_checker + consistency_checker.
These don't depend on each other and are cheap sanity passes.

Phase 2 (conditional): pricing_checker. Skipped when either phase-1
specialist returns a hard-fail (critical severity, high confidence) verdict,
since pricing a risk that's already being declined on coverage grounds, or
whose input data can't be trusted, wastes a call and can't be trusted anyway.
"""
import asyncio
from typing import List, Tuple

from app.agents import coverage_checker, consistency_checker, pricing_checker
from app.config import HARD_FAIL_MIN_CONFIDENCE, HARD_FAIL_SEVERITY, SEVERITY_WEIGHT


def worst_finding(verdict: dict) -> Tuple[str, float]:
    """Returns (severity, confidence) of the highest-severity finding in a
    verdict, breaking ties by confidence. Falls back to the verdict's own
    overall_severity/overall_confidence if there are no individual findings."""
    findings = verdict.get("findings", [])
    if not findings:
        return verdict.get("overall_severity", "info"), verdict.get("overall_confidence", 0.0)
    best = max(findings, key=lambda f: (SEVERITY_WEIGHT.get(f["severity"], 0), f["confidence"]))
    return best["severity"], best["confidence"]


def is_hard_fail(verdict: dict) -> bool:
    severity, confidence = worst_finding(verdict)
    return (
        SEVERITY_WEIGHT.get(severity, 0) >= SEVERITY_WEIGHT[HARD_FAIL_SEVERITY]
        and confidence >= HARD_FAIL_MIN_CONFIDENCE
    )


async def run(submission: dict) -> Tuple[List[dict], List[dict]]:
    """Returns (routing_steps, verdicts)."""
    routing_steps = []
    verdicts = []

    coverage_result, consistency_result = await asyncio.gather(
        coverage_checker.run(submission),
        consistency_checker.run(submission),
    )
    verdicts.extend([coverage_result, consistency_result])
    routing_steps.append({
        "phase": 1,
        "specialists_invoked": ["coverage_checker", "consistency_checker"],
        "reason": (
            "Always run in parallel: both are independent, low-cost sanity checks "
            "over the raw submission and don't depend on each other's output."
        ),
    })

    coverage_fail = is_hard_fail(coverage_result)
    consistency_fail = is_hard_fail(consistency_result)

    if coverage_fail or consistency_fail:
        culprit = coverage_result if coverage_fail else consistency_result
        severity, confidence = worst_finding(culprit)
        top_finding = max(
            culprit.get("findings", []),
            key=lambda f: (SEVERITY_WEIGHT.get(f["severity"], 0), f["confidence"]),
        )
        reason = (
            f"Skipped pricing_checker — {culprit['specialist']} returned a "
            f"{severity} finding (confidence {confidence:.2f}): \"{top_finding['finding']}\". "
            + (
                "Pricing a risk that coverage review already flags for decline is moot."
                if coverage_fail
                else "Pricing against data that isn't internally trustworthy isn't meaningful."
            )
        )
        routing_steps.append({"phase": 2, "specialists_invoked": [], "reason": reason})
    else:
        pricing_result = await pricing_checker.run(submission)
        verdicts.append(pricing_result)
        routing_steps.append({
            "phase": 2,
            "specialists_invoked": ["pricing_checker"],
            "reason": (
                "Ran pricing_checker — neither coverage_checker nor consistency_checker "
                "returned a hard-fail signal, so premium adequacy is still relevant."
            ),
        })

    return routing_steps, verdicts
