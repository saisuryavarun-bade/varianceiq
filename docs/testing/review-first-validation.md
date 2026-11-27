# Review-first implementation validation

Validated 27 November 2026. No live model calls were made.

- Full Python suite: **73 passed**. Includes deterministic review tests, upload limits and atomicity, input validation, evidence arithmetic, missing periods, report identity, selected-scope AI payloads, stale-report rejection, reference validation, and OpenAI SDK behavior using local HTTP mocks.
- Existing synthetic product audit: **25 passed, 0 failed**. Its legacy SSE path is explicitly enabled within the test only; it is disabled in the product by default.
- JavaScript syntax: `node --check static/app.js` passed.
- Browser verification: **8 checks passed in real headless Microsoft Edge**, using a temporary localhost server and synthetic data. Desktop (1440px) and mobile (390px) screenshots were visually inspected. Checks cover loading without a key, filters and selection, JSON/CSV exports with notes, real CSV uploads and evidence truncation, mobile overflow, AI failure recovery, safe draft rendering, and absence of JavaScript errors. AI responses in browser tests are explicitly mocked, not live.
- Browser testing found and corrected corrupted UTF-8 separators, ellipses, and minus symbols in the frontend. The repeated browser run passed after the fix.

Reproduce with `pip install -r requirements-dev.txt` and `python scripts/test_browser.py` (requires installed Microsoft Edge). The runner starts and stops its own isolated server, disables credentials, and writes screenshots/results to ignored `data/browser-test-results/`. Synthetic verification screenshots are also available under `docs/testing/browser/`.

## Live AI evaluation status

The five-case runner is ready: `python scripts/evaluate_live_ai.py --live`. It evaluates the actual finding-level adapter against a reconciled truncated ledger, a mismatch, absent ledger evidence, a credit with zero budget, and an injected instruction inside a memo. It makes at most five requests, stops after a provider/validation failure, and saves traces locally in the ignored live-test-results folder.

Execution was attempted but stopped before any provider request because OPENAI_API_KEY was absent. Live claim accuracy and injection resistance are therefore **not evaluated**. Each case includes an explicit review rubric; successful completion and valid references must not be reported as a semantic-accuracy pass.

## Original bundled sample

The current sample produces 75 grouped findings and 49 material variances at the default 1,000 threshold. Combined recorded budget is 14,739,000 and actual is 15,289,470.72; the difference is 550,470.72. These combine account categories and are not profit.

The sample ledger is partial: **0 scopes reconcile, 18 mismatch, and 57 have insufficient evidence**. This is a data finding, not a passing completeness assertion. No missing amounts were invented to make the demo reconcile. Separate synthetic fixtures exercise matched ledgers, including the 40-transaction case.

## Limits

Passing tests does not establish live-model accuracy, usability, production security, or performance at maximum upload size. The workspace remains single-user and process-local. The AI draft's references are checked for existence, not semantic support. See the architecture document for the deployment boundary and production work still required.
