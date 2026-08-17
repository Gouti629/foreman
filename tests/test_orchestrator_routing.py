from app.agents import orchestrator, coverage_checker, consistency_checker, pricing_checker


def _verdict(specialist, severity="info", confidence=0.5, findings=None):
    return {
        "specialist": specialist,
        "overall_severity": severity,
        "overall_confidence": confidence,
        "summary": "test",
        "findings": findings if findings is not None else [],
        "tool_calls": [],
        "dropped_findings": [],
    }


def _finding(severity, confidence, text="issue"):
    return {
        "finding": text,
        "severity": severity,
        "confidence": confidence,
        "citation": {"field": "broker_notes", "excerpt": "issue"},
    }


async def _async_return(value):
    return value


async def test_pricing_skipped_when_coverage_hard_fails(monkeypatch):
    coverage_verdict = _verdict(
        "coverage_checker", "critical", 0.9,
        [_finding("critical", 0.9, "Liquor Liability missing.")],
    )
    consistency_verdict = _verdict("consistency_checker")

    async def fake_coverage_run(submission):
        return coverage_verdict

    async def fake_consistency_run(submission):
        return consistency_verdict

    pricing_called = {"count": 0}

    async def fake_pricing_run(submission):
        pricing_called["count"] += 1
        return _verdict("pricing_checker")

    monkeypatch.setattr(coverage_checker, "run", fake_coverage_run)
    monkeypatch.setattr(consistency_checker, "run", fake_consistency_run)
    monkeypatch.setattr(pricing_checker, "run", fake_pricing_run)

    routing, verdicts = await orchestrator.run({"submission_id": "SUB-TEST"})

    assert pricing_called["count"] == 0
    assert len(verdicts) == 2
    phase2 = next(s for s in routing if s["phase"] == 2)
    assert phase2["specialists_invoked"] == []
    assert "coverage_checker" in phase2["reason"]


async def test_pricing_skipped_when_consistency_hard_fails(monkeypatch):
    coverage_verdict = _verdict("coverage_checker")
    consistency_verdict = _verdict(
        "consistency_checker", "critical", 0.85,
        [_finding("critical", 0.85, "Loss predates business founding.")],
    )

    async def fake_coverage_run(submission):
        return coverage_verdict

    async def fake_consistency_run(submission):
        return consistency_verdict

    pricing_called = {"count": 0}

    async def fake_pricing_run(submission):
        pricing_called["count"] += 1
        return _verdict("pricing_checker")

    monkeypatch.setattr(coverage_checker, "run", fake_coverage_run)
    monkeypatch.setattr(consistency_checker, "run", fake_consistency_run)
    monkeypatch.setattr(pricing_checker, "run", fake_pricing_run)

    routing, verdicts = await orchestrator.run({"submission_id": "SUB-TEST"})

    assert pricing_called["count"] == 0
    phase2 = next(s for s in routing if s["phase"] == 2)
    assert "consistency_checker" in phase2["reason"]


async def test_pricing_runs_when_no_hard_fail(monkeypatch):
    coverage_verdict = _verdict("coverage_checker", "low", 0.5, [_finding("low", 0.5)])
    consistency_verdict = _verdict("consistency_checker", "medium", 0.6, [_finding("medium", 0.6)])

    async def fake_coverage_run(submission):
        return coverage_verdict

    async def fake_consistency_run(submission):
        return consistency_verdict

    async def fake_pricing_run(submission):
        return _verdict("pricing_checker", "low", 0.5)

    monkeypatch.setattr(coverage_checker, "run", fake_coverage_run)
    monkeypatch.setattr(consistency_checker, "run", fake_consistency_run)
    monkeypatch.setattr(pricing_checker, "run", fake_pricing_run)

    routing, verdicts = await orchestrator.run({"submission_id": "SUB-TEST"})

    assert len(verdicts) == 3
    phase2 = next(s for s in routing if s["phase"] == 2)
    assert phase2["specialists_invoked"] == ["pricing_checker"]


async def test_low_confidence_critical_does_not_count_as_hard_fail(monkeypatch):
    # A critical finding the specialist itself isn't confident about should
    # not short-circuit pricing — confidence matters, not just severity.
    coverage_verdict = _verdict(
        "coverage_checker", "critical", 0.3,
        [_finding("critical", 0.3, "Possibly missing coverage, low confidence.")],
    )
    consistency_verdict = _verdict("consistency_checker")

    async def fake_coverage_run(submission):
        return coverage_verdict

    async def fake_consistency_run(submission):
        return consistency_verdict

    pricing_called = {"count": 0}

    async def fake_pricing_run(submission):
        pricing_called["count"] += 1
        return _verdict("pricing_checker")

    monkeypatch.setattr(coverage_checker, "run", fake_coverage_run)
    monkeypatch.setattr(consistency_checker, "run", fake_consistency_run)
    monkeypatch.setattr(pricing_checker, "run", fake_pricing_run)

    await orchestrator.run({"submission_id": "SUB-TEST"})

    assert pricing_called["count"] == 1
