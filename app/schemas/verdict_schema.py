"""The shared 'submit_verdict' tool schema every specialist is forced to call.

Forcing a tool call (rather than asking for free-text JSON) is what makes the
output structurally reliable: every finding must carry a severity, a
confidence, and a citation pointing back at the submission, or the tool call
itself is malformed and gets rejected before it reaches the database.
"""

SEVERITIES = ["info", "low", "medium", "high", "critical"]


def verdict_tool_schema(specialist_name: str) -> dict:
    return {
        "name": "submit_verdict",
        "description": (
            "Submit your structured verdict for this submission. Every finding must "
            "include a citation pointing to the exact submission field and value that "
            "justifies it. Do not include a finding you cannot cite."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "specialist": {
                    "type": "string",
                    "enum": [specialist_name],
                    "description": "Must be your own specialist identity.",
                },
                "overall_severity": {"type": "string", "enum": SEVERITIES},
                "overall_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Your confidence in the overall verdict, 0.0-1.0.",
                },
                "summary": {
                    "type": "string",
                    "description": "One plain-English sentence summarizing your verdict.",
                },
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding": {"type": "string"},
                            "severity": {"type": "string", "enum": SEVERITIES},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "citation": {
                                "type": "object",
                                "properties": {
                                    "field": {
                                        "type": "string",
                                        "description": (
                                            "Dotted path into the submission JSON you were "
                                            "given, e.g. 'requested_coverages[0].limit' or "
                                            "'loss_history[1].incurred_amount'."
                                        ),
                                    },
                                    "excerpt": {
                                        "type": "string",
                                        "description": "The actual value/text at that field.",
                                    },
                                },
                                "required": ["field", "excerpt"],
                            },
                        },
                        "required": ["finding", "severity", "confidence", "citation"],
                    },
                },
            },
            "required": ["specialist", "overall_severity", "overall_confidence", "summary", "findings"],
        },
    }
