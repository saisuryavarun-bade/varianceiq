# VarianceIQ — evidence-first financial review

Upload budget-versus-actuals data and review calculated variances, transaction reconciliation, and missing evidence. The entire review works without an API key. Optional OpenAI assistance produces a separate, unverified draft for one selected finding.

## Run locally

Requires Python 3.10 or later.

```bash
python -m venv .venv
# Activate .venv using your shell's activation command.
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The fictional bundled dataset loads immediately. Docker users can run `docker compose up --build`; the host port is bound to localhost and no key is required.

## Review workflow

1. Load the sample or upload a budget CSV and, optionally, transaction CSV.
2. Select a period and an absolute materiality threshold.
3. Inspect ranked findings, prior-month comparisons, and evidence gaps.
4. Expand transaction evidence and source references. Add analyst notes and a personal reviewed marker.
5. Export a JSON packet containing the complete loaded input, calculation policy, findings, references, notes, and any AI drafts. CSV export includes all findings in the selected report, not just the search-filtered rows.
6. Optionally request an AI draft for a selected finding. Only its evidence packet is sent to OpenAI. Citation existence is checked; factual support and causal claims remain subject to human review.

Notes are held in the browser tab and lost on reload unless exported. They are not authenticated approvals. A JSON export includes all loaded periods because comparisons depend on prior-period data; handle the packet as financial data.

## Input contract

Budget CSV: `period,department,account,budget,actual`.

Optional transaction CSV: `date,period,department,account,vendor,amount,memo`.

Periods use YYYY-MM. Missing, nonnumeric, and nonfinite financial amounts are rejected. Negative amounts and observed zeros are valid. Each file is limited to 5 MB, with at most 1,000 budget rows and 20,000 transaction rows. Materiality thresholds must be between zero and 1e18. Without a ledger, reconciliation is insufficient evidence, never a verified zero.

Variance is actual minus budget. The UI uses neutral above/below budget labels because account classification is not supplied. Combined revenue and expense totals are not profit. No currency is inferred or converted.

## Optional AI

Run `python scripts/configure_model.py` in a terminal to enter an OpenAI key without echo. It is saved in the ignored local .env. Restart the server. OPENAI_MODEL defaults to gpt-4.1-mini.

The finding-level action makes one request, caps output at 2,500 tokens, disables SDK retries, and allows one concurrent request per server process. Requests use store=false. That is not a claim of zero provider retention. Model access and API credits are required. No live accuracy results are claimed.

The earlier unrestricted SSE agent is retained only as an experimental baseline and disabled by default. ENABLE_LEGACY_AGENT=true explicitly enables it; the new UI never calls it.

## Validation

```bash
python -m pytest -q
python scripts/test_synthetic_product.py
```

Tests exercise deterministic arithmetic, missing data, snapshots, upload atomicity and limits, selected evidence scope, stale-report rejection, citation checks, and SDK behavior using local mocks. The synthetic script also tests the legacy SSE baseline under explicit opt-in. Neither makes live model calls.

## Deployment boundary

This is a private, single-user prototype. One dataset is held in memory per process; there is no authentication, durable audit log, or tenant isolation. Run one worker locally. Do not expose uploads publicly. Existing Render configuration is historical deployment scaffolding, not a production-security guarantee.

See [architecture](docs/architecture.md), [evidence contract](docs/evidence-contract.md), and [model testing](docs/model-testing.md). Before public use, implement authenticated ownership, persistent isolated storage, deployment-wide quotas, retention/deletion controls, and operational monitoring.
