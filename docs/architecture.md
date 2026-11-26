# Architecture

## Data and request lifecycle

The FastAPI server keeps one active in-memory pandas DataStore per process. POST /api/upload accepts budget_file and transactions_file CSVs. Validation rejects missing columns, empty budget data, malformed periods, missing grouping labels, and nonfinite or nonnumeric amounts before replacing the active store. This is a single-user prototype: uploads are shared across clients of that process, not isolated sessions.

GET /api/investigate opens an SSE stream and binds a VarianceAgent to the current store. The agent calls OpenAI's Responses API with six function tools. Tools calculate results locally; model-selected arguments determine which dataset slices are returned to OpenAI. No arbitrary SQL or code execution is exposed.

## Model loop

Each turn streams visible response text, gathers function calls, validates that arguments decode to a JSON object, and dispatches tools. Function results are sent back with the matching call_id. All response output items are retained for continuation. Optional tool arguments remain optional through explicit strict=false. The request uses store=false; this setting does not mean no provider processing or retention under applicable API policies.

The loop ends with a nonempty final response or an error when the configured turn budget is exhausted. Provider errors, incomplete responses, empty text, and prematurely closed streams do not emit successful completion. Provider exception bodies are not exposed to the browser. The SDK client closes when the generator finishes or is closed.

## Streaming contract

The existing frontend receives status, thinking (visible text deltas, not private reasoning), tool_call, tool_result, final, done, and error events. No frontend event migration is required.

## Evidence

Financial arithmetic, source-row references, full-slice totals, and reconciliation are implemented by local tools. Missing comparison periods are explicitly reported with null comparisons. See evidence-contract.md for limits. A successful API call does not establish narrative accuracy or causal truth; review the real-model trace against known synthetic outcomes.

## Configuration and tests

OPENAI_API_KEY is server-side only; OPENAI_MODEL defaults to gpt-4.1-mini and can be changed to a compatible model. Docker Compose and Render use these same variables. No Anthropic credentials are used.

Unit tests use the actual OpenAI SDK with a local HTTP mock serving SSE events. The synthetic product audit separately exercises upload, tools, and the application's SSE orchestration using a scripted provider. Neither requires a live key. See model-testing.md for the separately invoked live investigation.
