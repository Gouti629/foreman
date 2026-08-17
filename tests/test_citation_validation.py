from app.claude_client import resolve_dotted_path, validate_citation


def test_resolve_dotted_path_simple_key():
    assert resolve_dotted_path({"broker_notes": "hello"}, "broker_notes") == "hello"


def test_resolve_dotted_path_nested_index():
    context = {"requested_coverages": [{"type": "General Liability", "limit": 1000000}]}
    assert resolve_dotted_path(context, "requested_coverages[0].limit") == 1000000
    assert resolve_dotted_path(context, "requested_coverages[0].type") == "General Liability"


def test_resolve_dotted_path_missing_key_raises():
    try:
        resolve_dotted_path({"a": 1}, "b")
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_resolve_dotted_path_out_of_range_raises():
    try:
        resolve_dotted_path({"items": [1]}, "items[5]")
        assert False, "expected IndexError"
    except IndexError:
        pass


def test_validate_citation_true_when_excerpt_matches_value():
    context = {"broker_notes": "No alcohol served on premises."}
    assert validate_citation(context, "broker_notes", "No alcohol served on premises.") is True


def test_validate_citation_true_for_substring_match():
    context = {"broker_notes": "No alcohol served on premises, single location."}
    assert validate_citation(context, "broker_notes", "No alcohol served") is True


def test_validate_citation_false_when_field_missing():
    context = {"broker_notes": "hello"}
    assert validate_citation(context, "nonexistent_field", "hello") is False


def test_validate_citation_false_when_excerpt_does_not_match_value():
    context = {"requested_annual_premium": 38000}
    assert validate_citation(context, "requested_annual_premium", "a completely unrelated claim") is False


def test_validate_citation_false_for_fabricated_field_not_in_scoped_context():
    # Even if this field exists on the full submission, a specialist's citation
    # must resolve within the *scoped* context it was actually given.
    scoped_context = {"business_type": "Nightclub"}
    assert validate_citation(scoped_context, "requested_annual_premium", "38000") is False
