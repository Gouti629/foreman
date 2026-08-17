# Foreman — Evaluation Summary

**Not yet generated.** This repo was built without a live `ANTHROPIC_API_KEY` in the
build environment, so the 20 fixture submissions in `data/submissions/submissions.json`
have not been run through the real pipeline yet.

To generate this report:

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
pip install -r requirements.txt
python -m eval.run_eval
```

This overwrites this file with a real accuracy score, a confusion matrix against each
fixture's `known_label`, a routing-efficiency breakdown (how often the pricing check was
correctly skipped on hard-fail cases), and a per-submission detail table.
