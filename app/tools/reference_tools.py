"""Reference-data lookups exposed to specialist agents as Claude tools.

Keeping this data out of prompts (and behind a tool call) means the model
has to explicitly retrieve a specific class code's facts before it can cite
them, which is what makes the "no unsupported claims" requirement enforceable:
we can see exactly which lookups happened and cross-check findings against
the returned data.
"""
import json
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "reference")

with open(os.path.join(_DATA_DIR, "class_codes.json"), encoding="utf-8") as f:
    _CLASS_CODES = json.load(f)["class_codes"]

with open(os.path.join(_DATA_DIR, "comparable_pricing.json"), encoding="utf-8") as f:
    _PRICING = json.load(f)
    _PRICING_TABLE = _PRICING["pricing_table"]


def revenue_band(annual_revenue):
    if annual_revenue < 1_000_000:
        return "<1M"
    if annual_revenue < 5_000_000:
        return "1M-5M"
    if annual_revenue < 20_000_000:
        return "5M-20M"
    return "20M+"


def lookup_class_code(class_code: str) -> dict:
    entry = _CLASS_CODES.get(class_code)
    if entry is None:
        return {
            "found": False,
            "class_code": class_code,
            "known_class_codes": sorted(_CLASS_CODES.keys()),
        }
    return {"found": True, "class_code": class_code, **entry}


def lookup_comparable_pricing(class_code: str, annual_revenue: float) -> dict:
    band = revenue_band(annual_revenue)
    table_entry = _PRICING_TABLE.get(class_code)
    if table_entry is None:
        return {
            "found": False,
            "class_code": class_code,
            "known_class_codes": sorted(_PRICING_TABLE.keys()),
        }
    rate_min, rate_max = table_entry[band]
    return {
        "found": True,
        "class_code": class_code,
        "revenue_band": band,
        "premium_rate_range": [rate_min, rate_max],
        "expected_premium_range": [
            round(annual_revenue * rate_min, 2),
            round(annual_revenue * rate_max, 2),
        ],
    }


# --- Claude tool schemas -----------------------------------------------

LOOKUP_CLASS_CODE_TOOL = {
    "name": "lookup_class_code",
    "description": (
        "Look up reference facts for an industry class code: label, description, "
        "typical coverages for that class, common exclusions/red flags, and the "
        "typical revenue-per-employee range for businesses in that class."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "class_code": {
                "type": "string",
                "description": "The industry_class_code value from the submission, e.g. 'RESTAURANT-FULL'.",
            }
        },
        "required": ["class_code"],
    },
}

LOOKUP_COMPARABLE_PRICING_TOOL = {
    "name": "lookup_comparable_pricing",
    "description": (
        "Look up the typical annual premium range for comparable bound risks, given an "
        "industry class code and annual revenue. Returns the premium rate range (as a "
        "fraction of revenue) and the resulting expected dollar premium range for this "
        "specific revenue figure."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "class_code": {
                "type": "string",
                "description": "The industry_class_code value from the submission, e.g. 'CONTRACTOR-ROOFING'.",
            },
            "annual_revenue": {
                "type": "number",
                "description": "The submission's stated annual revenue in dollars.",
            },
        },
        "required": ["class_code", "annual_revenue"],
    },
}

TOOL_HANDLERS = {
    "lookup_class_code": lambda args: lookup_class_code(args["class_code"]),
    "lookup_comparable_pricing": lambda args: lookup_comparable_pricing(
        args["class_code"], args["annual_revenue"]
    ),
}
