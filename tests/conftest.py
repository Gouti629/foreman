import pytest


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        # messages is mutated by the caller after this returns (tool loop
        # appends further turns to the same list), so snapshot it now.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)


class FakeAsyncClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


def tool_use_block(name, input_, block_id="toolu_1"):
    return {"type": "tool_use", "id": block_id, "name": name, "input": input_}


@pytest.fixture
def sample_submission():
    return {
        "submission_id": "SUB-TEST",
        "business_name": "Test Bar Co.",
        "business_type": "Nightclub with full bar service.",
        "industry_class_code": "BAR-NIGHTCLUB",
        "annual_revenue": 1200000,
        "employee_count": 18,
        "years_in_business": 3,
        "location": {"city": "Miami", "state": "FL"},
        "requested_coverages": [
            {"type": "General Liability", "limit": 1000000, "deductible": 2500},
        ],
        "requested_annual_premium": 38000,
        "loss_history": [],
        "broker_notes": "Nightclub with full bar service.",
        "known_label": "decline",
    }
