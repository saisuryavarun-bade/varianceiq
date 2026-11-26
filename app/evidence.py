"""Source-linked drill-down evidence. Accounting checks do not establish causality."""
from __future__ import annotations

from decimal import Decimal
import hashlib
from typing import Any

from app.data_loader import DataStore


def exact_amount(value: Any) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("Evidence amounts must be finite numbers.")
    return amount


def transaction_evidence(
    store: DataStore, period: str, department: str, account: str, limit: int
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    txn = store.transactions
    # Fingerprint the ordered snapshot, not a caller-controlled DataFrame index.
    snapshot = txn.to_json(orient="split", index=False, date_format="iso", double_precision=15)
    snapshot_id = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    matches = (
        txn["period"].eq(period)
        & txn["department"].str.casefold().eq(department.casefold())
        & txn["account"].str.casefold().eq(account.casefold())
    )
    rows = []
    for position, matched in enumerate(matches):
        if not matched:
            continue
        row = txn.iloc[position]
        amount = exact_amount(row["amount"])
        rows.append({
            "source_id": f"txn:{snapshot_id}:{position + 1}",
            "source_row": position + 1,
            "date": str(row["date"]), "period": str(row["period"]),
            "department": str(row["department"]), "account": str(row["account"]),
            "vendor": str(row["vendor"]), "memo": str(row["memo"]),
            "amount_exact": format(amount, "f"),
        })
    rows.sort(key=lambda row: abs(Decimal(row["amount_exact"])), reverse=True)
    shown = rows[:limit]
    total = sum((Decimal(r["amount_exact"]) for r in rows), Decimal(0))
    subtotal = sum((Decimal(r["amount_exact"]) for r in shown), Decimal(0))

    ba = store.budget_actuals
    booked = ba[
        ba["period"].eq(period)
        & ba["department"].str.casefold().eq(department.casefold())
        & ba["account"].str.casefold().eq(account.casefold())
    ]
    actual = sum((exact_amount(v) for v in booked["actual"]), Decimal(0)) if len(booked) else None
    difference = total - actual if actual is not None else None
    if not rows or actual is None:
        status = "insufficient_evidence"
    else:
        status = "matched" if difference == 0 else "mismatch"
    return {
        "dataset_snapshot_sha256": snapshot_id,
        "matching_transaction_count": len(rows),
        "transaction_count": len(shown),
        "is_truncated": len(shown) < len(rows),
        "total_amount_exact": format(total, "f"),
        "returned_amount_exact": format(subtotal, "f"),
        "transactions": shown,
        "reconciliation": {
            "status": status,
            "budget_actual_rows": len(booked),
            "booked_actual_exact": format(actual, "f") if actual is not None else None,
            "ledger_minus_actual_exact": format(difference, "f") if difference is not None else None,
            "scope": "All matching loaded transactions versus matching booked actuals; exact decimal equality, no tolerance.",
        },
        "evidence_limits": [
            "Source rows are 1-based data rows in the identified ordered transaction snapshot, excluding a file header.",
            "The snapshot fingerprint identifies loaded data; it does not authenticate the original ledger.",
            "A matched sum does not prove source completeness, factual correctness, or the cause of a variance.",
            "Amounts are decimal representations of loaded values; parsing may already have lost source precision.",
        ],
    }
