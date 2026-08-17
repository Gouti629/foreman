"""Thin wrapper around the Anthropic SDK: a generic tool-use loop that lets a
specialist agent call reference-data tools zero or more times and then is
forced to call `submit_verdict` to finish. Also owns citation validation,
which is what turns "structured output" into "no unsupported claims."
"""
import re
from typing import Any, Callable, Dict, List, Optional

from anthropic import AsyncAnthropic

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from app.schemas.verdict_schema import verdict_tool_schema

_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class SpecialistError(RuntimeError):
    pass


def get_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


def _block_to_dict(block: Any) -> dict:
    if isinstance(block, dict):
        return block
    return block.model_dump()


def resolve_dotted_path(obj: Any, path: str):
    """Resolve a path like 'requested_coverages[0].limit' against a dict/list tree."""
    current = obj
    for name, idx in _PATH_TOKEN_RE.findall(path):
        if name:
            if not isinstance(current, dict) or name not in current:
                raise KeyError(path)
            current = current[name]
        else:
            i = int(idx)
            if not isinstance(current, list) or i >= len(current):
                raise IndexError(path)
            current = current[i]
    return current


def validate_citation(context: dict, field: str, excerpt: str) -> bool:
    """A citation is valid if its field path resolves within the context the
    specialist was actually given, and the cited excerpt is genuinely derived
    from that value (substring match, case-insensitive, either direction)."""
    try:
        value = resolve_dotted_path(context, field)
    except (KeyError, IndexError, ValueError):
        return False
    value_str = str(value).strip().lower()
    excerpt_str = str(excerpt).strip().lower()
    if not value_str or not excerpt_str:
        return False
    return value_str in excerpt_str or excerpt_str in value_str


async def run_specialist(
    specialist_name: str,
    system_prompt: str,
    user_message: str,
    context: dict,
    reference_tools: List[dict],
    tool_handlers: Dict[str, Callable[[dict], dict]],
    max_turns: int = 6,
) -> dict:
    """Runs the tool-use loop for one specialist and returns a dict shaped
    like app.models.SpecialistVerdict (as a plain dict, findings filtered to
    only those whose citations validate against `context`)."""
    client = get_client()
    tools = list(reference_tools) + [verdict_tool_schema(specialist_name)]
    messages: List[dict] = [{"role": "user", "content": user_message}]
    tool_call_trace: List[dict] = []

    for _turn in range(max_turns):
        response = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system_prompt,
            tools=tools,
            tool_choice={"type": "any"},
            messages=messages,
        )
        content_blocks = [_block_to_dict(b) for b in response.content]
        messages.append({"role": "assistant", "content": content_blocks})

        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
        submit_block = next((b for b in tool_use_blocks if b["name"] == "submit_verdict"), None)

        if submit_block is not None:
            verdict = dict(submit_block["input"])
            # The schema's `specialist` enum only ever allows one value for a
            # given call, but models don't always echo required fields back
            # reliably — set it from the known-good value rather than trust
            # the model included it.
            verdict["specialist"] = specialist_name
            verdict["tool_calls"] = tool_call_trace
            verdict["dropped_findings"] = []
            kept_findings = []
            for finding in verdict.get("findings", []):
                citation = finding.get("citation", {})
                if validate_citation(context, citation.get("field", ""), citation.get("excerpt", "")):
                    kept_findings.append(finding)
                else:
                    verdict["dropped_findings"].append(finding)
            verdict["findings"] = kept_findings
            return verdict

        if not tool_use_blocks:
            # Model produced only text and didn't call a tool. Nudge it once.
            messages.append({
                "role": "user",
                "content": "You must call the submit_verdict tool to finish. Call it now.",
            })
            continue

        tool_results = []
        for block in tool_use_blocks:
            handler = tool_handlers.get(block["name"])
            if handler is None:
                result: Any = {"error": f"unknown tool {block['name']}"}
            else:
                result = handler(block["input"])
            tool_call_trace.append({"tool": block["name"], "input": block["input"], "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": [{"type": "text", "text": _to_text(result)}],
            })
        messages.append({"role": "user", "content": tool_results})

    raise SpecialistError(f"{specialist_name} did not submit a verdict within {max_turns} turns")


def _to_text(result: Any) -> str:
    import json
    return json.dumps(result)
