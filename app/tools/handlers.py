"""Tool implementations.

The agent calls these via Claude's native tool-use API. Each handler takes a JSON
input dict and returns a JSON-serializable dict. All work is done against pandas
DataFrames held in the in-memory `DataStore`.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.data_loader import DataStore
from app.evidence import transaction_evidence


def _format_currency(value: float) -> str:
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{sign}${abs_value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{sign}${abs_value / 1_000:.0f}K"
    return f"{sign}${abs_value:.0f}"


def get_dataset_overview(store: DataStore) -> dict[str, Any]:
    df = store.budget_actuals
    txn = store.transactions

    periods = sorted(df["period"].unique().tolist())
    return {
        "row_count": int(len(df)),
        "transaction_count": int(len(txn)),
        "period_range": f"{periods[0]} to {periods[-1]}" if periods else "n/a",
        "periods": periods,
        "departments": sorted(df["department"].unique().tolist()),
        "accounts": sorted(df["account"].unique().tolist()),
        "total_budget": _format_currency(float(df["budget"].sum())),
        "total_actual": _format_currency(float(df["actual"].sum())),
        "total_variance": _format_currency(float((df["actual"] - df["budget"]).sum())),
    }


def query_variances(
    store: DataStore,
    period: str | None = None,
    department: str | None = None,
    account: str | None = None,
    min_abs_variance: float = 50_000,
    min_abs_variance_pct: float = 0.15,
    limit: int = 20,
) -> dict[str, Any]:
    df = store.budget_actuals.copy()

    if period:
        if period.upper() == "YTD":
            pass  # all periods
        elif "Q" in period.upper():
            year, q = period.upper().split("-Q")
            quarter_months = {
                "1": ["01", "02", "03"],
                "2": ["04", "05", "06"],
                "3": ["07", "08", "09"],
                "4": ["10", "11", "12"],
            }
            months = quarter_months.get(q, [])
            df = df[df["period"].isin([f"{year}-{m}" for m in months])]
        else:
            df = df[df["period"] == period]

    if department:
        df = df[df["department"].str.lower() == department.lower()]
    if account:
        df = df[df["account"].str.lower() == account.lower()]

    if df.empty:
        return {"variances": [], "note": "No matching rows."}

    df = df.assign(
        variance=df["actual"] - df["budget"],
        variance_pct=lambda x: (x["actual"] - x["budget"])
        / x["budget"].replace(0, pd.NA),
    )

    df = df[
        (df["variance"].abs() >= min_abs_variance)
        | (df["variance_pct"].abs() >= min_abs_variance_pct)
    ]

    df = df.reindex(df["variance"].abs().sort_values(ascending=False).index)
    df = df.head(limit)

    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "period": r["period"],
                "department": r["department"],
                "account": r["account"],
                "budget": _format_currency(float(r["budget"])),
                "actual": _format_currency(float(r["actual"])),
                "variance": _format_currency(float(r["variance"])),
                "variance_pct": (
                    f"{r['variance_pct'] * 100:+.1f}%"
                    if pd.notna(r["variance_pct"])
                    else "n/a"
                ),
                "direction": ("Over budget" if r["variance"] > 0 else
                              "Under budget" if r["variance"] < 0 else "On budget"),
            }
        )

    return {
        "variance_count": len(rows),
        "filters": {
            "period": period,
            "department": department,
            "account": account,
            "min_abs_variance": min_abs_variance,
            "min_abs_variance_pct": min_abs_variance_pct,
        },
        "variances": rows,
    }


def drill_down_variance(
    store: DataStore,
    period: str,
    department: str,
    account: str,
    limit: int = 25,
) -> dict[str, Any]:
    evidence = transaction_evidence(store, period, department, account, limit)
    for row in evidence["transactions"]:
        row["amount"] = _format_currency(float(row["amount_exact"]))
    return {
        "period": period, "department": department, "account": account,
        **evidence,
        "total_amount": _format_currency(float(evidence["total_amount_exact"])),
        "returned_amount": _format_currency(float(evidence["returned_amount_exact"])),
    }


def summarize_vendor_spend(
    store: DataStore,
    period: str,
    department: str | None = None,
    account: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    txn = store.transactions.copy()
    if period.upper() != "YTD":
        txn = txn[txn["period"] == period]
    if department:
        txn = txn[txn["department"].str.lower() == department.lower()]
    if account:
        txn = txn[txn["account"].str.lower() == account.lower()]

    if txn.empty:
        return {"vendors": [], "note": "No transactions match."}

    grouped = (
        txn.groupby("vendor")["amount"]
        .agg(["sum", "count"])
        .reset_index()
        .rename(columns={"sum": "total_spend", "count": "transaction_count"})
        .sort_values("total_spend", key=lambda s: s.abs(), ascending=False)
        .head(limit)
    )

    vendors = []
    for _, r in grouped.iterrows():
        vendors.append(
            {
                "vendor": r["vendor"],
                "total_spend": _format_currency(float(r["total_spend"])),
                "transaction_count": int(r["transaction_count"]),
            }
        )

    return {
        "period": period,
        "vendor_count": len(vendors),
        "vendors": vendors,
    }


def compare_period_over_period(
    store: DataStore,
    period_a: str,
    period_b: str,
    department: str | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    df = store.budget_actuals.copy()
    if department:
        df = df[df["department"].str.lower() == department.lower()]
    if account:
        df = df[df["account"].str.lower() == account.lower()]

    a = df[df["period"] == period_a]
    b = df[df["period"] == period_b]

    missing = [period for period, rows in ((period_a, a), (period_b, b)) if rows.empty]
    if missing:
        return {
            "period_a": period_a, "period_b": period_b,
            "filters": {"department": department, "account": account},
            "missing_periods": list(dict.fromkeys(missing)),
            "actual_a": _format_currency(float(a["actual"].sum())) if not a.empty else None,
            "actual_b": _format_currency(float(b["actual"].sum())) if not b.empty else None,
            "delta": None, "delta_pct": None,
            "note": "Cannot compare: no matching records for one or more periods. Missing data is not zero.",
        }

    actual_a = float(a["actual"].sum())
    actual_b = float(b["actual"].sum())
    delta = actual_b - actual_a
    delta_pct = (delta / actual_a) if actual_a else None

    return {
        "period_a": period_a,
        "period_b": period_b,
        "filters": {"department": department, "account": account},
        "actual_a": _format_currency(actual_a),
        "actual_b": _format_currency(actual_b),
        "delta": _format_currency(delta),
        "delta_pct": (
            f"{delta_pct * 100:+.1f}%" if delta_pct is not None else "n/a"
        ),
    }


def compose_executive_summary(
    store: DataStore, investigation_complete: bool = True
) -> dict[str, Any]:
    return {
        "ready_to_write": investigation_complete,
        "checklist": [
            "1. Headline: total variance and the 2-3 largest drivers in one sentence.",
            "2. Drivers section: for each material variance, name the period, "
            "department, account, dollar amount, percentage, and the SPECIFIC "
            "transaction-level driver you identified.",
            "3. Severity flags: any variance pattern that suggests controls issues, "
            "duplicate payments, or unauthorized spend.",
            "4. Recommended actions: 2-4 concrete next steps for the FP&A team.",
            "5. Format as clean markdown with headers. No preamble or meta-commentary.",
        ],
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS = {
    "get_dataset_overview": get_dataset_overview,
    "query_variances": query_variances,
    "drill_down_variance": drill_down_variance,
    "summarize_vendor_spend": summarize_vendor_spend,
    "compare_period_over_period": compare_period_over_period,
    "compose_executive_summary": compose_executive_summary,
}


def dispatch_tool(name: str, args: dict[str, Any], store: DataStore) -> dict[str, Any]:
    """Route a tool call to its handler. Unknown tools return an error payload."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return handler(store, **args)
    except TypeError as exc:
        return {"error": f"Bad arguments to {name}: {exc}"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{type(exc).__name__}: {exc}"}
