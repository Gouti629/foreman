import app.claude_client as claude_client
from app.claude_client import run_specialist
from tests.conftest import FakeAsyncClient, FakeResponse, tool_use_block


def _verdict_block(specialist, findings, block_id="toolu_verdict"):
    return tool_use_block(
        "submit_verdict",
        {
            "specialist": specialist,
            "overall_severity": "critical" if findings else "info",
            "overall_confidence": 0.9,
            "summary": "test summary",
            "findings": findings,
        },
        block_id=block_id,
    )


async def test_happy_path_calls_reference_tool_then_submits_verdict(monkeypatch):
    context = {"industry_class_code": "BAR-NIGHTCLUB", "broker_notes": "Full bar, no liquor liability requested."}
    lookup_call = tool_use_block("lookup_class_code", {"class_code": "BAR-NIGHTCLUB"}, block_id="toolu_1")
    finding = {
        "finding": "Liquor Liability missing for a bar class.",
        "severity": "critical",
        "confidence": 0.9,
        "citation": {"field": "broker_notes", "excerpt": "no liquor liability requested"},
    }
    responses = [
        FakeResponse([lookup_call]),
        FakeResponse([_verdict_block("coverage_checker", [finding])]),
    ]
    fake_client = FakeAsyncClient(responses)
    monkeypatch.setattr(claude_client, "get_client", lambda: fake_client)

    verdict = await run_specialist(
        specialist_name="coverage_checker",
        system_prompt="test system prompt",
        user_message="test user message",
        context=context,
        reference_tools=[{"name": "lookup_class_code", "description": "", "input_schema": {}}],
        tool_handlers={"lookup_class_code": lambda args: {"found": True, "class_code": args["class_code"]}},
    )

    assert verdict["specialist"] == "coverage_checker"
    assert len(verdict["findings"]) == 1
    assert verdict["dropped_findings"] == []
    assert len(verdict["tool_calls"]) == 1
    assert verdict["tool_calls"][0]["tool"] == "lookup_class_code"
    # two API calls: one that produced the tool_use, one that produced submit_verdict
    assert len(fake_client.messages.calls) == 2


async def test_finding_with_uncitable_field_is_dropped(monkeypatch):
    context = {"broker_notes": "Nightclub, full bar."}
    bad_finding = {
        "finding": "Made-up claim about a field that isn't in scope.",
        "severity": "critical",
        "confidence": 0.95,
        "citation": {"field": "requested_annual_premium", "excerpt": "38000"},
    }
    responses = [FakeResponse([_verdict_block("coverage_checker", [bad_finding])])]
    fake_client = FakeAsyncClient(responses)
    monkeypatch.setattr(claude_client, "get_client", lambda: fake_client)

    verdict = await run_specialist(
        specialist_name="coverage_checker",
        system_prompt="test",
        user_message="test",
        context=context,
        reference_tools=[],
        tool_handlers={},
    )

    assert verdict["findings"] == []
    assert len(verdict["dropped_findings"]) == 1


async def test_model_text_only_response_is_nudged_to_call_submit_verdict(monkeypatch):
    context = {"broker_notes": "All good here."}
    text_only = FakeResponse([{"type": "text", "text": "Let me think about this."}])
    verdict_response = FakeResponse([_verdict_block("coverage_checker", [])])
    fake_client = FakeAsyncClient([text_only, verdict_response])
    monkeypatch.setattr(claude_client, "get_client", lambda: fake_client)

    verdict = await run_specialist(
        specialist_name="coverage_checker",
        system_prompt="test",
        user_message="test",
        context=context,
        reference_tools=[],
        tool_handlers={},
    )

    assert verdict["specialist"] == "coverage_checker"
    assert len(fake_client.messages.calls) == 2
    # the nudge message should have been appended before the second call
    second_call_messages = fake_client.messages.calls[1]["messages"]
    assert "submit_verdict" in second_call_messages[-1]["content"]
