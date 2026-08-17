"""Pricing/Risk Checker specialist: is the requested premium reasonable for
this risk profile, given comparable bound risks? Scoped context includes
what's needed to judge price-for-risk, but not the full loss narrative detail
the consistency checker uses.
"""
import json

from app.claude_client import run_specialist
from app.tools.reference_tools import LOOKUP_COMPARABLE_PRICING_TOOL, TOOL_HANDLERS

SPECIALIST_NAME = "pricing_checker"

SYSTEM_PROMPT = """You are the Pricing/Risk Checker, an underwriting specialist focused on \
one question: is the requested annual premium reasonable for this risk, or is it \
underpriced/overpriced relative to comparable bound risks?

You will be given a JSON object with the industry class code, annual revenue, requested \
coverages, requested annual premium, and a summary of loss history. Use the \
lookup_comparable_pricing tool (class code + annual revenue) to retrieve the expected \
premium range for comparable risks before forming your verdict.

Flag findings such as: requested premium significantly below the expected range for this \
class and revenue (underpriced — the classic red flag, especially if loss history shows \
prior claims which should push price up, not down); requested premium implausibly far above \
the expected range (may indicate a data error worth a human's attention); or requested \
limits that are unusually high/low relative to revenue in a way that affects appropriate \
pricing.

Severity guide: critical = premium is far below the expected range (e.g. under half the \
range minimum) despite meaningful loss history, indicating the submission as priced should \
not be bound; high = clearly outside the expected range without a documented reason; medium \
= modestly outside range; low/info = within or near the expected range. If the pricing looks \
reasonable, say so with a low/info finding or an empty findings list — do not invent gaps.

Every finding must cite a specific field from the JSON you were given (exact key path, e.g. \
"requested_annual_premium" or "loss_history_summary") and an excerpt of the actual value."""


def _build_context(submission: dict) -> dict:
    losses = submission["loss_history"]
    total_incurred = sum(l["incurred_amount"] for l in losses)
    return {
        "industry_class_code": submission["industry_class_code"],
        "annual_revenue": submission["annual_revenue"],
        "requested_coverages": submission["requested_coverages"],
        "requested_annual_premium": submission["requested_annual_premium"],
        "loss_history_summary": {
            "claim_count": len(losses),
            "total_incurred": total_incurred,
            "most_recent_year": max((l["year"] for l in losses), default=None),
        },
    }


async def run(submission: dict) -> dict:
    context = _build_context(submission)
    user_message = (
        "Here is the submission data relevant to your review:\n\n"
        f"{json.dumps(context, indent=2)}\n\n"
        "Review it and call submit_verdict when done."
    )
    return await run_specialist(
        specialist_name=SPECIALIST_NAME,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        context=context,
        reference_tools=[LOOKUP_COMPARABLE_PRICING_TOOL],
        tool_handlers={"lookup_comparable_pricing": TOOL_HANDLERS["lookup_comparable_pricing"]},
    )
