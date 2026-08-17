"""Coverage Checker specialist: does the requested coverage make sense for
this business type and its stated exposures? Scoped context excludes
pricing and loss-history detail — this agent only judges coverage fit.
"""
import json

from app.claude_client import run_specialist
from app.tools.reference_tools import LOOKUP_CLASS_CODE_TOOL, TOOL_HANDLERS

SPECIALIST_NAME = "coverage_checker"

SYSTEM_PROMPT = """You are the Coverage Checker, an underwriting specialist focused on one \
question: does the coverage this broker is requesting make sense for this business's \
industry and stated exposures?

You will be given a JSON object describing the business type, industry class code, years \
in business, the coverages being requested, and any broker notes. Use the \
lookup_class_code tool to retrieve the typical coverages and common exclusions/red flags \
for this class before forming your verdict — do not rely on general knowledge alone.

Flag findings such as: a coverage that is standard/mandatory for this class but missing \
from the request; a coverage being requested that doesn't match the business type at all; \
limits that are structurally nonsensical (e.g. zero or missing); or broker notes that \
describe an exposure (e.g. serving alcohol, working at height, caring for children) with no \
corresponding coverage requested.

Severity guide: critical = the coverage as requested is fundamentally inappropriate for \
this risk (a mandatory coverage for this class is entirely absent); high = an important gap \
that a human underwriter must resolve before binding; medium = a gap worth flagging but not \
disqualifying; low/info = minor or purely informational observations.

Every finding must cite a specific field from the JSON you were given (using its exact key \
path, e.g. "requested_coverages[0].type" or "broker_notes") and an excerpt of the actual \
value. Only make a finding you can point to something specific for. If coverage looks \
appropriate, say so with a low/info finding or an empty findings list — do not invent gaps."""


def _build_context(submission: dict) -> dict:
    return {
        "business_name": submission["business_name"],
        "business_type": submission["business_type"],
        "industry_class_code": submission["industry_class_code"],
        "years_in_business": submission["years_in_business"],
        "requested_coverages": submission["requested_coverages"],
        "broker_notes": submission["broker_notes"],
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
        reference_tools=[LOOKUP_CLASS_CODE_TOOL],
        tool_handlers={"lookup_class_code": TOOL_HANDLERS["lookup_class_code"]},
    )
