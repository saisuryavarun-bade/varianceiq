# Review-first implementation validation

Validated 27 November 2026. No live model calls were made.

- Full Python suite: **73 passed**. Includes deterministic review tests, upload limits and atomicity, input validation, evidence arithmetic, missing periods, report identity, selected-scope AI payloads, stale-report rejection, reference validation, and OpenAI SDK behavior using local HTTP mocks.
- Existing synthetic product audit: **25 passed, 0 failed**. Its legacy SSE path is explicitly enabled within the test only; it is disabled in the product by default.
- JavaScript syntax: `node --check static/app.js` passed.
- Browser preview: local server started successfully, but the browser automation runtime failed before opening a page with a missing kernel-assets path. Layout and interactive browser behavior remain unverified.

## Original bundled sample

The current sample produces 75 grouped findings and 49 material variances at the default 1,000 threshold. Combined recorded budget is 14,739,000 and actual is 15,289,470.72; the difference is 550,470.72. These combine account categories and are not profit.

The sample ledger is partial: **0 scopes reconcile, 18 mismatch, and 57 have insufficient evidence**. This is a data finding, not a passing completeness assertion. No missing amounts were invented to make the demo reconcile. Separate synthetic fixtures exercise matched ledgers, including the 40-transaction case.

## Limits

Passing tests does not establish live-model accuracy, usability, production security, or performance at maximum upload size. The workspace remains single-user and process-local. The AI draft's references are checked for existence, not semantic support. See the architecture document for the deployment boundary and production work still required.
