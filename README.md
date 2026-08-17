# Foreman

Foreman is a multi-agent orchestration system for insurance broker submission review. A
broker submits a commercial P&C application; Foreman routes it through three specialist
Claude agents, decides which of them are even worth running, and synthesizes their
findings into one traceable decision — **accept**, **decline**, or **refer to a human
underwriter** — with a confidence score and a rationale a human can read in ten seconds.

This is a portfolio project demonstrating the orchestration pattern used when coordinating
several autonomous specialists around a single business decision: route to the right
specialist, run independent specialists in parallel, short-circuit work that's no longer
relevant, and synthesize the results into something a human can audit.

## Architecture

```
                         ┌───────────────────────────┐
                         │     Broker Submission       │
                         │   (raw JSON application)    │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌───────────────────────────┐
                         │        Orchestrator          │
                         │  (deterministic routing code, │
                         │   not a 4th LLM call — see     │
                         │   "why this design" below)     │
                         └──────────────┬───────────────┘
                                        │
                   Phase 1 — always run, concurrently
              ┌─────────────────────────┴─────────────────────────┐
              ▼                                                     ▼
  ┌──────────────────────────┐                        ┌──────────────────────────┐
  │     Coverage Checker       │                        │    Consistency Checker     │
  │     Claude + tool call     │                        │     Claude + tool call     │
  │  sees: business type,      │                        │  sees: revenue, headcount, │
  │  class code, requested     │                        │  location, loss history,   │
  │  coverages, broker notes   │                        │  broker notes               │
  │  tool: lookup_class_code   │                        │  tool: lookup_class_code    │
  └──────────────┬──────────────┘                        └──────────────┬──────────────┘
                 │                                                       │
                 └───────────────────────┬───────────────────────────────┘
                                         ▼
                   hard-fail? (a finding at critical severity,
                        ≥0.7 confidence, from either check)
                     │                                    │
                    yes                                   no
                     │                                    │
                     ▼                                    ▼
          skip Pricing Checker                 ┌──────────────────────────┐
        (reason logged in the trace)            │    Pricing/Risk Checker    │
                     │                           │     Claude + tool call     │
                     │                           │  sees: premium, revenue,   │
                     │                           │  coverage limits, loss     │
                     │                           │  history summary            │
                     │                           │  tool: lookup_comparable_   │
                     │                           │  pricing                    │
                     │                           └──────────────┬──────────────┘
                     │                                          │
                     └────────────────────┬─────────────────────┘
                                          ▼
                         ┌───────────────────────────┐
                         │          Synthesis            │
                         │  deterministic weighted score  │
                         │  + templated rationale over     │
                         │  the actual findings             │
                         └──────────────┬───────────────┘
                                        ▼
                   accept / decline / refer + confidence + rationale
                            (persisted to SQLite as a full trace)
                                        │
                                        ▼
                         ┌───────────────────────────┐
                         │         Dashboard              │
                         │  submission list → orchestration │
                         │  trace → decision                 │
                         └───────────────────────────┘
```

## Why this design

**The orchestrator's routing is deterministic code, not a fourth LLM call.** The one part
of this system that has to be cheap and auditable is *which specialists ran and why*. An
LLM call that decides routing before it has looked at any specialist's output would be
guessing; code that reads the actual severity and confidence Phase 1 returned is not. The
routing rule is simple and stated once, in [`app/agents/orchestrator.py`](app/agents/orchestrator.py):
run Coverage + Consistency in parallel (they're independent, cheap sanity checks), then
skip Pricing only if either of those returned a critical finding it's actually confident
about. Skipping saves an API call on submissions that are already headed for decline or
whose numbers can't be trusted anyway, and every skip is logged with the specific finding
that caused it — visible in the dashboard's orchestration trace, not buried in a log file.

**Specialists are scoped, not given the raw submission.** Each specialist's system prompt
and context (see `_build_context` in each file under [`app/agents/`](app/agents)) includes
only the fields relevant to its question. Coverage Checker never sees the requested
premium; Pricing Checker never sees broker notes about staffing. This isn't just tidiness —
it's what makes the citation-validation step meaningful: a citation only counts if it
resolves inside the *scoped* context the model actually received, so a specialist can't
launder a finding by pointing at data it was never given.

**Every finding must be cited, and citations are verified in code, not trusted.**
Specialists are forced (via `tool_choice`) to call a `submit_verdict` tool whose schema
requires a `citation.field` (a dotted path into the submission JSON) and `citation.excerpt`
for every finding. After the model responds, [`app/claude_client.py`](app/claude_client.py)
resolves that field path against the real scoped context and checks the excerpt actually
matches the value there. Findings that fail this check are dropped from the verdict and
recorded separately as `dropped_findings` — visible in the dashboard as evidence the
system enforces "no unsupported claims" rather than just asking nicely for it.

**Synthesis is a formula, not a fifth LLM call.** The combined confidence score and the
accept/decline/refer decision come from `app/agents/synthesis.py`: each specialist's worst
finding contributes a score (`severity_weight × confidence`), the loudest score decides the
decision via two fixed thresholds, and the combined confidence is a weighted average where
specialists with more severe findings count for more (a confident critical finding
dominates a confident-but-unremarkable one — not a plain average). The rationale sentence
is built from a template over the *actual* driving finding, so it can never say something
the verdicts underneath it don't support. This also means the decision math is fully
unit-testable without hitting the API (see `tests/test_synthesis.py`).

**Reference data lives behind tool calls, not in prompts.** The industry class-code table
and comparable-pricing table (`data/reference/`) are only reachable through
`lookup_class_code` and `lookup_comparable_pricing`. This forces the model to make an
explicit, loggable retrieval before it can cite that data, and keeps the reference data
itself easy to extend without touching prompts.

**Storage is SQLite with JSON columns.** This is a portfolio-scale app — a `submissions`
table and a `runs` table, each storing one JSON blob per row, is easier to read end-to-end
than a normalized schema would be, and the dashboard only ever needs "list" and "get by id."

**No Node.js was available in the build environment**, so the dashboard is plain HTML/CSS/JS
served as static files by FastAPI — no build step, no bundler, nothing to install beyond
`pip install -r requirements.txt`.

## Repo layout

```
app/
  agents/
    coverage_checker.py      specialist: does requested coverage fit the risk?
    pricing_checker.py       specialist: is the requested premium reasonable?
    consistency_checker.py   specialist: does the submission agree with itself?
    orchestrator.py          routing: who runs, in what order, and why
    synthesis.py             deterministic scoring -> decision + confidence + rationale
  schemas/verdict_schema.py  the forced-tool-call schema every specialist must answer with
  tools/reference_tools.py   class-code + comparable-pricing lookups, exposed as Claude tools
  claude_client.py           tool-use loop + citation validation
  db.py                      SQLite storage (submissions, runs)
  run_pipeline.py            glue: submission -> orchestrator -> synthesis -> persisted trace
  main.py                    FastAPI app: dashboard + JSON API
data/
  reference/                 class_codes.json, comparable_pricing.json (tool-backed lookups)
  submissions/                20 synthetic test submissions with known-correct labels
eval/
  run_eval.py                 runs the fixtures live, scores accuracy + routing efficiency
  eval_report.md               generated report (placeholder until run with a live key)
dashboard/                    static HTML/CSS/JS orchestration-trace viewer
tests/                        offline unit tests (mocked Claude client, no API key needed)
```

## Setup

Requires Python 3.9+.

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash / macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

uvicorn app.main:app --reload
```

Then open http://localhost:8000. The 20 fixture submissions load automatically on
startup; click one and hit **Run live** to invoke the real orchestrator end-to-end.

### Running the offline test suite

No API key required — the Claude client is mocked throughout:

```bash
pytest -q
```

Covers: citation-path resolution and validation, the specialist tool-use loop (including a
dropped-finding case and a text-only-response nudge case), orchestrator routing
(short-circuit and non-short-circuit paths), and every synthesis decision boundary.

### Running the evaluation

Requires a live `ANTHROPIC_API_KEY`. Runs all 20 fixtures through the real pipeline and
overwrites `eval/eval_report.md` with accuracy, a confusion matrix against each fixture's
`known_label`, and a routing-efficiency breakdown:

```bash
python -m eval.run_eval
```

## Test dataset

`data/submissions/submissions.json` has 20 synthetic submissions: 5 clean accepts, 8
clear declines (a mix of hard coverage gaps like missing Liquor Liability on a bar, and
hard pricing gaps like a roofing quote priced at half the expected range despite two fall
claims), 7 ambiguous refers, and 4 of those are adversarial — internally inconsistent data
(broker notes claiming "no prior losses" while a loss sits right there in `loss_history`;
a loss dated before the business existed) or surface-clean submissions with a hidden red
flag (a roofing contractor whose revenue-per-employee is 2x the typical max, implying
understated headcount, even though coverage and pricing both look fine in isolation).

## Known assumptions / what to check when you run it

- Built without a live `ANTHROPIC_API_KEY` in the dev environment, so `eval/eval_report.md`
  is a placeholder — run `python -m eval.run_eval` to generate the real numbers.
- Severity/confidence thresholds in `app/config.py` and `app/agents/synthesis.py` were
  chosen deliberately but are the most likely thing to want tuning after seeing real model
  output on the fixture set.
