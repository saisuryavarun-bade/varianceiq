# Architecture

## Request lifecycle

1. **Upload** — `POST /api/upload` accepts a `budget_vs_actuals` CSV and an optional `transactions` CSV. The server creates a fresh `DataStore` (a new in-memory DuckDB), validates and normalizes columns, computes `variance_amount` / `variance_pct` if missing, and returns a session ID plus a summary ribbon of stats.

2. **Investigate** — `GET /api/investigate/{session_id}` opens a Server-Sent Events stream. The route constructs an `Agent` bound to the session's DataStore and yields events from the agent loop in real time:

   ```
   status     → high-level lifecycle messages
   thinking   → free-text reasoning the model emitted between tool calls
   tool_call  → name + arguments of a tool the model invoked
   tool_result→ matched to its tool_call by id
   finding    → a confirmed insight (parallel to a record_finding tool call)
   report     → the final executive memo
   done       → terminal event with turn / finding counts
   error      → any failure
   ```

3. **Browser** consumes events via `EventSource`, renders the agent's reasoning into the left panel, and grows the findings/report panel on the right.

## Why a custom agent loop

Most agent demos lean on LangChain or LlamaIndex. Two reasons VarianceIQ doesn't:

1. **Transparency for reviewers.** The whole loop is in `app/agent.py`. There is no hidden prompt, no wrapper class, no abstraction layer. Anyone can read it in 60 seconds and know what's happening.
2. **Streaming control.** We need fine-grained events emitted *between* tool calls — not just final answers. Frameworks make this awkward.

The loop is a textbook implementation of Anthropic's tool-use protocol:

```python
while turn < MAX_TURNS:
    response = await client.messages.create(
        model=MODEL,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=conversation,
    )
    for block in response.content:
        if block.type == "text":
            stream("thinking", block.text)
        elif block.type == "tool_use":
            stream("tool_call", block)
            result = execute_tool(block.name, block.input, store, state)
            stream("tool_result", result)
            collect_into_next_user_turn(result)

    if state.report is not None:        # finalize_report was called
        break
```

## Data isolation

Each upload creates a brand-new in-memory DuckDB instance. There is no cross-session table, no shared state, and no way for one user's queries to see another's data. This is enforced by `DataStore.__init__` which calls `duckdb.connect(":memory:")` — this is per-process-thread isolated by DuckDB itself.

## SQL safety

The agent has full SQL expressivity, but the runtime checks every query against an allowlist (`SELECT`, `WITH`, `DESCRIBE`, `SHOW`, `EXPLAIN`, `PRAGMA`) and rejects anything containing forbidden tokens (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `ATTACH`, `COPY`). DuckDB itself enforces a hard limit on result-set size in the application code (max 200 rows returned to the model).

## Streaming protocol

`sse-starlette`'s `EventSourceResponse` emits events with the SSE `event:` field set to the event kind (`thinking`, `tool_call`, etc.). The frontend registers one handler per kind via `addEventListener`, which avoids string-discriminator parsing on the client.

## Failure modes and recovery

| Failure | Response |
|---|---|
| Model produces malformed JSON for tool input | Anthropic SDK validates against `input_schema` and returns an error the model can read |
| SQL syntax error | Returned as `{error: "..."}` to the model — agent retries |
| Forbidden write SQL | Same. Agent retries with a SELECT |
| Model exceeds turn budget | `error` event is sent and stream closes |
| Client disconnects | `request.is_disconnected()` is checked each iteration; loop aborts |
| Anthropic API failure | Caught by the publisher, surfaced as an `error` event with type info |
