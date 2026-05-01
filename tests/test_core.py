"""Tests for data layer, tools, and API endpoints. No LLM calls required."""
from __future__ import annotations

from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BA_PATH = DATA_DIR / "sample_budget_actuals.csv"
TXN_PATH = DATA_DIR / "sample_transactions.csv"


# ---------- data loader ----------

def test_sample_data_files_exist():
    assert BA_PATH.exists(), "Run scripts/generate_sample_data.py first"
    assert TXN_PATH.exists()


def test_load_sample_store():
    from app.data_loader import DataStore
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    assert len(store.budget_actuals) == 75
    assert len(store.transactions) == 78


def test_validate_rejects_missing_columns():
    from app.data_loader import DataStore
    import pandas as pd
    import io
    bad_ba = pd.read_csv(io.StringIO("period,department\n2025-07,Sales\n"))
    good_tx = pd.read_csv(TXN_PATH)
    with pytest.raises(ValueError, match="missing required columns"):
        DataStore._validate(bad_ba, good_tx)


def test_budget_actuals_columns():
    import pandas as pd
    df = pd.read_csv(BA_PATH)
    required = {"period", "department", "account", "budget", "actual"}
    assert required.issubset(set(df.columns))


def test_transactions_columns():
    import pandas as pd
    df = pd.read_csv(TXN_PATH)
    required = {"date", "period", "department", "account", "vendor", "amount", "memo"}
    assert required.issubset(set(df.columns))


# ---------- tools ----------

def test_get_dataset_overview():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("get_dataset_overview", {}, store)
    assert result["row_count"] == 75
    assert "Engineering" in result["departments"]
    assert "$" in result["total_budget"]


def test_query_variances_returns_results():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("query_variances", {
        "period": "YTD",
        "min_abs_variance": 25000,
        "min_abs_variance_pct": 0.05,
    }, store)
    assert result["variance_count"] > 0
    assert any(v["department"] == "Engineering" for v in result["variances"])


def test_drill_down_legal_fees():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("drill_down_variance", {
        "period": "2025-08",
        "department": "G&A",
        "account": "Legal Fees",
    }, store)
    assert result["transaction_count"] == 4
    vendors = [t["vendor"] for t in result["transactions"]]
    assert "Cooley LLP" in vendors


def test_summarize_vendor_spend():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("summarize_vendor_spend", {
        "period": "YTD",
        "department": "Marketing",
        "account": "Paid Search - Non-Brand",
    }, store)
    assert result["vendor_count"] > 0
    assert any("Google" in v["vendor"] for v in result["vendors"])


def test_compare_period_over_period():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("compare_period_over_period", {
        "period_a": "2025-07",
        "period_b": "2025-09",
        "department": "Engineering",
        "account": "Engineering Salaries",
    }, store)
    assert "$" in result["actual_a"]
    assert "$" in result["delta"]


def test_compose_executive_summary():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("compose_executive_summary", {"investigation_complete": True}, store)
    assert result["ready_to_write"] is True
    assert len(result["checklist"]) >= 3


def test_unknown_tool_returns_error():
    from app.data_loader import DataStore
    from app.tools import dispatch_tool
    store = DataStore.from_csv(BA_PATH, TXN_PATH)
    result = dispatch_tool("nonexistent_tool", {}, store)
    assert "error" in result


# ---------- API endpoints ----------

def test_health_endpoint():
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dataset_endpoint():
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/api/dataset")
    assert r.status_code == 200
    data = r.json()
    assert data["row_count"] == 75
    assert "Engineering" in data["departments"]


def test_index_serves_html():
    import os
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    from app.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "VarianceIQ" in r.text
