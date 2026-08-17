from app.agents.synthesis import synthesize


def _verdict(specialist, overall_confidence, findings):
    return {
        "specialist": specialist,
        "overall_severity": findings[0]["severity"] if findings else "info",
        "overall_confidence": overall_confidence,
        "summary": "test",
        "findings": findings,
    }


def _finding(severity, confidence, text="issue"):
    return {
        "finding": text,
        "severity": severity,
        "confidence": confidence,
        "citation": {"field": "x", "excerpt": "x"},
    }


def test_critical_high_confidence_finding_declines():
    verdicts = [
        _verdict("coverage_checker", 0.9, [_finding("critical", 0.9, "Liquor Liability missing.")]),
        _verdict("consistency_checker", 0.8, []),
    ]
    result = synthesize(verdicts)
    assert result["decision"] == "decline"
    assert "coverage_checker" in result["rationale"]


def test_no_findings_at_all_accepts():
    verdicts = [
        _verdict("coverage_checker", 0.9, []),
        _verdict("consistency_checker", 0.9, []),
        _verdict("pricing_checker", 0.9, []),
    ]
    result = synthesize(verdicts)
    assert result["decision"] == "accept"


def test_single_high_severity_moderate_confidence_refers():
    verdicts = [
        _verdict("coverage_checker", 0.6, [_finding("high", 0.6, "Umbrella missing for large contractor.")]),
        _verdict("consistency_checker", 0.9, []),
    ]
    result = synthesize(verdicts)
    assert result["decision"] == "refer"


def test_two_independent_medium_findings_refer_even_without_single_trigger():
    verdicts = [
        _verdict("coverage_checker", 0.6, [_finding("medium", 0.5, "Minor coverage gap.")]),
        _verdict("consistency_checker", 0.6, [_finding("medium", 0.5, "Revenue per employee slightly low.")]),
        _verdict("pricing_checker", 0.6, [_finding("low", 0.5, "Pricing marginally low.")]),
    ]
    result = synthesize(verdicts)
    assert result["decision"] == "refer"
    assert result["score_breakdown"]["medium_plus_finding_count"] == 2


def test_critical_finding_with_low_confidence_does_not_auto_decline():
    verdicts = [
        _verdict("coverage_checker", 0.3, [_finding("critical", 0.3, "Uncertain critical claim.")]),
        _verdict("consistency_checker", 0.9, []),
    ]
    result = synthesize(verdicts)
    assert result["decision"] != "decline"


def test_combined_confidence_weights_more_severe_specialist_more_heavily():
    # A confident critical finding should pull combined confidence toward its
    # own confidence more than a simple average of [0.95, 0.2] (0.575) would.
    verdicts = [
        _verdict("coverage_checker", 0.95, [_finding("critical", 0.95, "Big problem.")]),
        _verdict("consistency_checker", 0.2, [_finding("info", 0.2, "Trivial note.")]),
    ]
    result = synthesize(verdicts)
    simple_average = (0.95 + 0.2) / 2
    assert result["confidence"] > simple_average


def test_rationale_is_short_enough_to_read_in_ten_seconds():
    verdicts = [
        _verdict("coverage_checker", 0.9, [_finding("critical", 0.9, "Liquor Liability missing.")]),
    ]
    result = synthesize(verdicts)
    assert len(result["rationale"]) < 400
