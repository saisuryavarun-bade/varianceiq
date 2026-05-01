# Prompt Design Notes

## Why the system prompt matters more than the model

A generic LLM prompted "investigate this data" will produce variance commentary that looks competent but isn't useful. It will list every variance, miss the connections between them, fail to drill into root causes, and write in the kind of vague hedged language that gets a memo deleted.

Most of the quality of VarianceIQ comes from the system prompt encoding *how a senior FP&A analyst actually thinks*. The full prompt is in `app/prompts.py`. Three design choices are worth calling out.

## 1. Materiality thresholds, encoded explicitly

A junior analyst reports every variance. A senior analyst triages — anything under ~$25k or ~3% is usually noise. The prompt tells the agent this directly:

> Variances under ~$25k or under ~3% of the line are usually noise. Focus your time on:
> - Material expense overages (>$50k or >10%, whichever is larger)
> - Material revenue beats or misses (>2% of the line)
> - Patterns that span multiple periods
> - Variances that compound

Without this, the agent records 15 findings of $3k each. With it, the agent records 4–6 material findings and the memo is readable.

## 2. The "connect dots" instruction

This is the highest-leverage part of the prompt:

> Look for offsetting variances — e.g., salary underspend offset by contractor overage often means open reqs being covered by contractors. This narrative matters more than either number alone.

A naive agent reports "Engineering salaries underspent $217k" and "Engineering contractors overspent $78k" as two independent findings. A senior analyst reports them as one finding: "Open eng reqs being filled by contractors at a 2.8x premium to budgeted FTE comp." The latter is what a CFO actually wants.

The same principle applies to favorable variances — sales commission overage paired with revenue beat is healthy; cloud cost overage *without* revenue beat is a problem. The prompt teaches the agent to look for these pairings.

## 3. Termination via a structured tool

The naive way to end an agent loop is to look for "I'm done" in the model's text. This is fragile.

VarianceIQ uses a `finalize_report` tool that the agent calls exactly once. Its execution flips a flag in the `InvestigationState`, the loop checks the flag after each turn, and exits cleanly when set. This means:

- The end condition is unambiguous (a function call, not text parsing)
- The final memo is produced as structured arguments — `headline`, `executive_summary`, `recommended_actions` — which means the frontend can render them with proper typography instead of dumping a wall of text

## What I tried that didn't work

- **Asking for findings in JSON via text completion.** Worked ~80% of the time. The 20% that failed (extra commentary, malformed JSON, missing fields) made it not viable. Tool use solved this completely.
- **Single-tool `query` API.** I started with one tool that took a `query_type` enum. The agent kept picking the wrong type. Splitting into `get_schema`, `run_sql`, `record_finding`, and `finalize_report` made each tool's purpose unambiguous.
- **Letting the agent call `record_finding` mid-investigation OR after `finalize_report`.** Initially both worked, but the agent sometimes recorded a "finding" that contradicted the report. Now `finalize_report` errors if no findings exist, and the loop exits the moment it succeeds.
- **Higher SQL budget (50 calls).** The model would burn through queries on tangential drilling. 25 is a tight enough budget that the agent prioritizes — same memo quality, half the latency and cost.

## Cost note

A typical investigation on the bundled sample data uses ~12 turns and ~30k input + 5k output tokens. At Sonnet 4.6 pricing, that's well under $0.05 per investigation.
