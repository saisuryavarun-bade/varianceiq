# Transaction evidence contract

The drill-down now exposes exact decimal strings, snapshot-scoped source IDs, full matching counts and totals, returned-row subtotals, and a reconciliation against the booked actuals for the same period, department and account.

`transaction_count` continues to mean returned rows. `matching_transaction_count` counts the entire loaded slice. `total_amount` now describes that entire slice rather than the top-N display subset. Consumers needing the previous subset total should use `returned_amount`. Currency labels are for display only; use the `_exact` fields for calculations. Negative amounts are retained as credits/reversals, not discarded.

Source IDs contain the SHA-256 fingerprint of the ordered transaction snapshot and its 1-based data-row position. They remain the same across display limits and DataFrame-index changes. Reordering or editing the snapshot changes the fingerprint. The application does not persist historical snapshots; a citation identifies data but is not yet a durable archived evidence link. The fingerprint does not authenticate a source or prove a transaction is true.

Reconciliation is `matched`, `mismatch`, or `insufficient_evidence`. It compares all matching loaded transaction amounts with the sum of matching booked actuals using exact decimal equality and no tolerance. Missing booked rows or missing transactions yield insufficient evidence, not a verified zero. A mismatch may reflect an incomplete extract, different accounting treatment or a data error; it is not by itself misconduct. A matched amount does not establish causal support, original precision, complete source coverage, or correct currency treatment. All rows are assumed to use a common currency/unit as in the current application schema.

The frontend labels its eight-row preview separately from the full matching slice. The tool can return more rows than the UI preview; the source IDs remain in its structured output. The agent prompt requests citations and explicit uncertainty, but this is an instruction, not a deterministic guarantee that generated memos comply. No live LLM evaluation or human study is implied.

Run `python -m pytest tests/test_evidence.py -q` for hand-calculated examples of truncation, credits, exact decimal arithmetic, mismatches, missing evidence, duplicate DataFrame indices, snapshot changes and nonfinite inputs. Next research milestone: persist a run-level evidence bundle and evaluate actual generated claims against it, including cases outside these designed examples.
