"""Evidence contract tests use independent, hand-calculated accounting fixtures."""
import json
import pandas as pd
import pytest

from app.data_loader import DataStore
from app.tools.handlers import drill_down_variance


def store(amounts=(60.10, 30.20, -10.30), actual=80.0):
    ba = pd.DataFrame([dict(period="2026-09", department="Ops", account="Services", budget=70, actual=actual)])
    tx = pd.DataFrame([dict(date="2026-09-01", period="2026-09", department="Ops",
                            account="Services", vendor=f"Vendor {i}", amount=v, memo="Source description")
                       for i, v in enumerate(amounts)])
    return DataStore(ba, tx)


def drill(s, limit=25):
    return drill_down_variance(s, "2026-09", "ops", "services", limit)


def test_full_total_does_not_change_with_display_limit():
    s = store()
    short, full = drill(s, 1), drill(s)
    assert short["total_amount_exact"] == full["total_amount_exact"] == "80.0"
    assert short["returned_amount_exact"] == "60.1"
    assert short["matching_transaction_count"] == 3
    assert short["transaction_count"] == 1 and short["is_truncated"]
    assert short["reconciliation"]["status"] == "matched"
    assert short["transactions"][0]["source_id"] == full["transactions"][0]["source_id"]


def test_reconciliation_mismatch_and_exact_decimal_sums():
    r = drill(store((0.1, 0.2), 0.3))
    assert r["total_amount_exact"] == "0.3"
    assert r["reconciliation"]["status"] == "matched"
    mismatch = drill(store(actual=100))["reconciliation"]
    assert mismatch["status"] == "mismatch"
    assert mismatch["ledger_minus_actual_exact"] == "-20.0"


def test_no_records_is_not_a_verified_zero():
    s = store();s.transactions = s.transactions.iloc[:0]
    assert drill(s)["reconciliation"]["status"] == "insufficient_evidence"
    s = store();s.budget_actuals = s.budget_actuals.iloc[:0]
    assert drill(s)["reconciliation"]["booked_actual_exact"] is None
    assert drill(s)["reconciliation"]["status"] == "insufficient_evidence"


def test_source_positions_survive_duplicate_dataframe_indices():
    s = store();s.transactions.index = [4,4,4]
    r = drill(s)
    assert len({x["source_id"] for x in r["transactions"]}) == 3
    assert {x["source_row"] for x in r["transactions"]} == {1,2,3}


def test_snapshot_changes_if_evidence_is_edited():
    s = store();before = drill(s)
    s.transactions.loc[0,"memo"] = "Changed description"
    after = drill(s)
    assert before["dataset_snapshot_sha256"] != after["dataset_snapshot_sha256"]
    assert before["transactions"][0]["source_id"] != after["transactions"][0]["source_id"]


def test_other_periods_do_not_reconcile_this_slice():
    s = store();s.transactions.loc[0,"period"] = "2026-08"
    r = drill(s)
    assert r["matching_transaction_count"] == 2
    assert r["reconciliation"]["status"] == "mismatch"
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize("limit", [0,-1,1.5,True])
def test_invalid_limit_is_rejected(limit):
    with pytest.raises(ValueError, match="positive integer"):
        drill(store(), limit)


@pytest.mark.parametrize("amount", [float('nan'),float('inf'),-float('inf')])
def test_nonfinite_values_do_not_become_valid_evidence(amount):
    with pytest.raises(ValueError, match="finite"):
        drill(store((amount,), 0))
