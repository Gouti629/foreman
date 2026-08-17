"""Glue: run one submission end-to-end through orchestrator -> synthesis and
persist the resulting trace. This is the single entry point used by both the
FastAPI 'run live' endpoint and the eval script, so dashboard runs and eval
runs are guaranteed to go through identical logic.
"""
import uuid
from datetime import datetime, timezone

from app.agents import orchestrator, synthesis
from app.db import get_conn, save_run


async def run_submission(submission: dict, persist: bool = True) -> dict:
    routing_steps, verdicts = await orchestrator.run(submission)
    decision = synthesis.synthesize(verdicts)

    trace = {
        "run_id": f"RUN-{uuid.uuid4().hex[:10]}",
        "submission_id": submission["submission_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "routing": routing_steps,
        "verdicts": verdicts,
        "decision": decision,
        "known_label": submission.get("known_label"),
        "known_label_reason": submission.get("known_label_reason"),
    }

    if persist:
        with get_conn() as conn:
            save_run(conn, trace)

    return trace
