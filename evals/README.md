# Agent quality evaluation

The scenarios in `scenarios.json` are a small application-specific review set, not an agents-cli EvaluationDataset. They separate semantic agent quality from ordinary code correctness. They have **not been run**, because the API key and a working package/runtime installation were unavailable.

After installing dependencies and configuring `GEMINI_API_KEY`, run:

```powershell
uv run python -m evals.run
```

This writes model responses to ignored `evals/results.local.json`. Review each response against every listed criterion, recording pass/fail and evidence. Require all criteria to pass before relying on these behaviors; retain a redacted evaluation report. Compare reports whenever changing model or prompts. Expand with human-reviewed question/answer correctness, rubric consistency, unsupported questions, and fairness cases before classroom use. This initial review harness does not establish calibrated scoring, fairness, or production quality.
