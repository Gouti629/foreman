"""Consistency Checker specialist: do the submission's own numbers and
statements agree with each other? Scoped context deliberately excludes
requested coverage/premium — this agent judges internal data integrity, not
whether the ask is a good one.
"""
import json

from app.claude_client import run_specialist
from app.tools.reference_tools import LOOKUP_CLASS_CODE_TOOL, TOOL_HANDLERS

SPECIALIST_NAME = "consistency_checker"

SYSTEM_PROMPT = """You are the Consistency Checker, an underwriting specialist focused on \
one question: is this submission internally consistent, or do the stated facts contradict \
each other in ways that should raise scrutiny?

You will be given a JSON object with business type, industry class code, annual revenue, \
employee count, years in business, location, loss history, broker notes, and the current \
calendar year for date-plausibility checks. Use the lookup_class_code tool to retrieve the \
typical revenue-per-employee range for this class and compare it against the stated revenue \
and employee count.

Flag findings such as: revenue-per-employee wildly outside the typical range for this class \
(e.g. revenue far too high for headcount, suggesting understated headcount, or far too low, \
suggesting an inflated revenue figure); a loss event dated before the business could have \
existed (loss year earlier than current_year - years_in_business) or in the future; broker \
notes that state something ("no prior losses", "single location") contradicted by the \
structured fields (a non-empty loss_history, multiple locations implied elsewhere); or an \
employee count of zero/near-zero alongside meaningful revenue and no explanation.

Severity guide: critical = a hard contradiction that cannot both be true (e.g. broker notes \
claim no losses but loss_history is non-empty, or a loss predates the business); high = a \
number far enough outside plausible range to suggest an error or misrepresentation; medium = \
a modest inconsistency worth a human's attention; low/info = minor or informational. If the \
submission looks internally consistent, say so with a low/info finding or an empty findings \
list — do not invent contradictions.

Every finding must cite a specific field from the JSON you were given (exact key path, e.g. \
"loss_history[0].year" or "broker_notes") and an excerpt of the actual value."""


def _build_context(submission: dict, current_year: int) -> dict:
    return {
        "business_type": submission["business_type"],
        "industry_class_code": submission["industry_class_code"],
        "annual_revenue": submission["annual_revenue"],
        "employee_count": submission["employee_count"],
        "years_in_business": submission["years_in_business"],
        "location": submission["location"],
        "loss_history": submission["loss_history"],
        "broker_notes": submission["broker_notes"],
        "current_year": current_year,
    }


async def run(submission: dict, current_year: int = 2026) -> dict:
    context = _build_context(submission, current_year)
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
        reference_tools=[LOOKUP_CLASS_CODE_TOOL],
        tool_handlers={"lookup_class_code": TOOL_HANDLERS["lookup_class_code"]},
    )
