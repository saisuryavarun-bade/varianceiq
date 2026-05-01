# VarianceIQ — Autonomous FP&A Variance Investigation Agent

> Upload your Budget vs. Actuals. An autonomous agent investigates the numbers — drilling into departments, accounts, and transactions — and produces the executive memo your FP&A team would spend half a day on.

---

## What it does

VarianceIQ reproduces the workflow a senior FP&A analyst runs at every month-end close:

1. **Triage** — surface the largest variances by department and account
2. **Drill** — inspect transaction-level detail to identify the actual driver (vendor, campaign, project)
3. **Compare** — check whether a variance is a one-time spike or a sustained trend across periods
4. **Synthesize** — write a CFO-ready executive memo with dollar figures, root causes, and recommended actions

The agent is fully autonomous. You upload data, it investigates, and it produces a memo. Every step is streamed live to the UI so you can see exactly what it queried, what it found, and how it reasoned.

## Why this is interesting

- **Real agentic behavior, not a chatbot.** The agent uses native [Anthropic tool use](https://docs.claude.com/en/docs/agents-and-tools/tool-use/overview) to autonomously plan and execute a multi-step investigation. There is a custom orchestration loop — no LangChain, no LlamaIndex — so reviewers see exactly what happens in ~130 lines of [`app/agent.py`](app/agent.py).
- **6 purpose-built tools.** `get_dataset_overview`, `query_variances`, `drill_down_variance`, `summarize_vendor_spend`, `compare_period_over_period`, `compose_executive_summary`. Each tool has a clear behavioral description that shapes the agent's investigation strategy.
- **Production patterns.** SSE streaming, structured error payloads, graceful tool dispatch, bounded iteration limits, Docker + Render deploy config, CI on push.
- **Real domain logic.** The system prompt encodes how a senior analyst thinks (materiality thresholds, driver vs. symptom distinction, severity flags). The sample dataset has deliberately-planted variance patterns that produce a genuinely useful memo.

## Architecture

```
   ┌──────────────────────────┐
   │  Browser (vanilla JS)    │
   │  ─ uploads CSV           │
   │  ─ consumes SSE stream   │
   └────────────┬─────────────┘
                │  HTTP / SSE
   ┌────────────▼─────────────┐
   │  FastAPI                 │
   │  ─ /api/upload           │
   │  ─ /api/dataset          │
   │  ─ /api/investigate      │  (Server-Sent Events)
   └────────────┬─────────────┘
                │
   ┌────────────▼─────────────────────────────┐
   │  Agent loop (Anthropic native tool use)  │
   │                                          │
   │   plan ──► call tool ──► observe ──► …   │
   │                                          │
   └────────────┬─────────────────────────────┘
                │
   ┌────────────▼──────────────────────────┐
   │  Tool dispatcher                      │
   │   ─ get_dataset_overview              │  ┌─────────────────┐
   │   ─ query_variances                   │──► Pandas DataFrames│
   │   ─ drill_down_variance               │  │ (in-memory)     │
   │   ─ summarize_vendor_spend            │  └─────────────────┘
   │   ─ compare_period_over_period        │
   │   ─ compose_executive_summary         │
   └───────────────────────────────────────┘
```

## Quick start

### Option 1 — Docker (one command)

```bash
git clone https://github.com/<you>/varianceiq.git
cd varianceiq
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
docker compose up --build
```

Visit **http://localhost:8000** and click *Try the sample dataset*.

### Option 2 — Local Python

```bash
git clone https://github.com/<you>/varianceiq.git
cd varianceiq
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_sample_data.py
cp .env.example .env   # add your API key
uvicorn app.main:app --reload
```

You'll need an [Anthropic API key](https://console.anthropic.com). A typical investigation costs **under $0.05** with `claude-sonnet-4-6`.

## Bringing your own data

Upload two CSVs:

| File | Columns | Required |
|---|---|---|
| Budget vs Actuals | `period, department, account, budget, actual` | Yes |
| Transactions | `date, period, department, account, vendor, amount, memo` | Yes |

## What the sample investigation finds

The bundled dataset describes "Lumera Health" (fictional Series-C SaaS), Q3 2025. Variances are deliberately planted to produce a useful narrative:

- **Subscription revenue beat plan by ~6%** — enterprise renewals closed early
- **Engineering salaries underspent ~$217k** — four senior reqs unfilled all quarter
- **Engineering contractors overspent ~$78k** — backfill for those open reqs (offsetting, structural)
- **Paid Search Non-Brand overspent ~$138k** — Google Ads bid expansion across all three months
- **Legal fees overspent ~$63k** — one-time Cooley LLP vendor dispute settlement in August
- **Sales commissions overspent ~$56k** — favorable; tracks revenue beat

## Project layout

```
varianceiq/
├── app/
│   ├── main.py             # FastAPI app + SSE endpoint
│   ├── agent.py            # orchestration loop (~130 lines)
│   ├── tools/
│   │   ├── definitions.py  # tool schemas for Anthropic API
│   │   └── handlers.py     # tool implementations (pandas)
│   ├── data_loader.py      # CSV ingestion + validation
│   ├── prompts.py          # system prompt
│   └── config.py           # env-driven settings
├── static/                 # single-page app, no build step
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── scripts/
│   └── generate_sample_data.py
├── data/                   # generated sample CSVs
├── tests/                  # 15 tests, no LLM calls
├── docs/
│   ├── architecture.md
│   └── prompt_design.md
├── Dockerfile
├── docker-compose.yml
├── render.yaml             # one-click Render.com deploy
├── .github/workflows/test.yml
└── README.md
```

## Tests

```bash
pytest tests/ -v
```

15 tests covering data loading, column validation, all 6 tools, error handling, and API endpoints. Tests do not call the LLM, so they run in ~1 second offline.

## Tech choices

| Decision | Why |
|---|---|
| Anthropic native tool use (no LangChain) | Reviewers see the actual loop. ~130 lines, no hidden behavior. |
| 6 purpose-built tools (not raw SQL) | Each tool has a clear purpose. Fewer failure modes than free-form SQL. |
| Pandas in-memory | Zero infra. Simple. Fast for the dataset sizes FP&A teams work with. |
| SSE instead of WebSockets | Agent stream is one-way. SSE is simpler and survives proxies. |
| Vanilla JS frontend | One file, no build, recruiters can read every line. |
| Sonnet 4.6 default | Strong agentic tool use. ~$0.05 per investigation. |

## License

MIT

---

<p align="center"><sub>Built as a portfolio piece. Sample data is synthetic.</sub></p>
