# Synthetic product test report

Executed 26 November 2026 against the working tree based on commit `b6973653db8c77bf016937886a7fa1b634607883` (including local fixes).

**25 checks passed; 0 failed.**

These tests upload generated CSVs through the real FastAPI endpoint, invoke the real analytical tools and exercise the real agent/SSE loop with a scripted provider. No LLM calls, participant study or browser rendering test were performed.

| Check | Result | Severity | Expected |
|---|---|---|---|
| valid_upload | PASS | none | HTTP 200 |
| dataset_counts | PASS | none | 40 uploaded transactions |
| truncated_totals | PASS | none | Full total 40780; displayed subtotal 5185; 5 of 40 rows |
| matching_actuals | PASS | none | matched |
| citations_resolve_to_loaded_rows | PASS | none | Each source reference resolves to its actual uploaded row |
| variance_arithmetic | PASS | none | (40780-30000)/30000 = 35.933...% |
| vendor_aggregation | PASS | none | All 40 transactions counted across vendors |
| scripted_investigation_sse | PASS | none | Real agent loop executes 4 tools and emits final/done; provider is scripted |
| credit_reversal | PASS | none | Credit included; 100-20=80; matched |
| decimal_precision | PASS | none | 0.1+0.2 reconciles exactly with 0.3 |
| missing_record_detection | PASS | none | Ledger 150 versus booked 200 => mismatch |
| duplicate_changes_total | PASS | none | Duplicate changes ledger to 250 versus booked 150; mismatch, not deduplicated |
| wrong_period_exclusion | PASS | none | No in-period transactions => insufficient_evidence |
| empty_ledger_not_verified_zero | PASS | none | Empty ledger is not a verified zero |
| zero_budget_percentage | PASS | none | No division-by-zero; percentage n/a |
| zero_variance_direction | PASS | none | On budget for exactly zero variance |
| absent_period_is_not_zero | PASS | none | Explicit missing-period indication, not a fabricated zero actual |
| nonnumeric_actual_rejected | PASS | none | HTTP 400 for malformed financial input |
| missing_actual_rejected | PASS | none | HTTP 400 for malformed financial input |
| infinite_transaction_rejected | PASS | none | HTTP 400 for malformed financial input |
| invalid_period_rejected | PASS | none | HTTP 400 for malformed financial input |
| missing_column_rejected | PASS | none | HTTP 400 |
| failed_upload_is_atomic | PASS | none | Failed upload preserves prior store |
| reset_sample | PASS | none | Bundled sample restored after audit |
| missing_model_key_handled | PASS | none | HTTP 400 with configuration error |

## Reproduce

```bash
python scripts/test_synthetic_product.py
```

Exit code 1 signals detected product failures. Generated fixtures are under `tests/fixtures/synthetic_product/`; full observations are in `synthetic-product-results.json`. The script runs an isolated in-process application and resets its dataset at the end. It does not connect to a deployed server.

## Release interpretation

Passing deterministic checks establishes behavior only for these cases. Provider scripting verifies tool execution and event transport, not whether a real model selects the right tools, cites evidence correctly, resists malicious memos, or writes faithful conclusions. The original six failures are preserved in synthetic-product-before-fixes.json; consult the current results above for their status.
