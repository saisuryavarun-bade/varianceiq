"""Lightweight in-memory data store for budget/actuals + transactions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re

import pandas as pd

from app.config import get_settings


@dataclass
class DataStore:
    """Holds the two DataFrames the agent queries.

    Schemas
    -------
    budget_actuals: period (YYYY-MM), department, account, budget, actual
    transactions:   date (YYYY-MM-DD), period (YYYY-MM), department, account, vendor,
                    amount, memo
    """

    budget_actuals: pd.DataFrame
    transactions: pd.DataFrame
    source: str = "sample"

    @classmethod
    def from_csv(
        cls, budget_path: Path, transactions_path: Path, source: str = "upload"
    ) -> "DataStore":
        ba = pd.read_csv(budget_path)
        tx = pd.read_csv(transactions_path)
        cls._validate(ba, tx)
        return cls(budget_actuals=ba, transactions=tx, source=source)

    @classmethod
    def from_excel(
        cls, path: Path, source: str = "upload"
    ) -> "DataStore":
        # Expect two sheets: 'budget_actuals' and 'transactions'
        sheets = pd.read_excel(path, sheet_name=None)
        try:
            ba = sheets["budget_actuals"]
            tx = sheets["transactions"]
        except KeyError as exc:
            raise ValueError(
                "Excel upload must contain sheets named 'budget_actuals' and "
                "'transactions'."
            ) from exc
        cls._validate(ba, tx)
        return cls(budget_actuals=ba, transactions=tx, source=source)

    @staticmethod
    def _validate(ba: pd.DataFrame, tx: pd.DataFrame) -> None:
        ba_required = {"period", "department", "account", "budget", "actual"}
        tx_required = {"date", "period", "department", "account", "vendor", "amount", "memo"}
        missing_ba = ba_required - set(ba.columns)
        missing_tx = tx_required - set(tx.columns)
        if missing_ba:
            raise ValueError(
                f"budget_actuals is missing required columns: {sorted(missing_ba)}"
            )
        if missing_tx:
            raise ValueError(
                f"transactions is missing required columns: {sorted(missing_tx)}"
            )
        if ba.empty:
            raise ValueError("budget_actuals must contain at least one row.")
        for name, frame, amounts in (
            ("budget_actuals", ba, ("budget", "actual")),
            ("transactions", tx, ("amount",)),
        ):
            for column in ("period", "department", "account"):
                values = frame[column]
                if values.isna().any() or values.map(lambda v: not isinstance(v, str) or not v.strip()).any():
                    raise ValueError(f"{name}.{column} must contain nonempty text.")
            if not frame["period"].map(lambda v: bool(re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", v))).all():
                raise ValueError(f"{name}.period must use a valid YYYY-MM month.")
            for column in amounts:
                values = frame[column]
                numeric = pd.to_numeric(values, errors="coerce")
                if values.map(lambda v: isinstance(v, bool)).any() or not numeric.map(
                    lambda v: pd.notna(v) and math.isfinite(float(v))
                ).all():
                    raise ValueError(f"{name}.{column} must contain finite numeric amounts; missing values are not allowed.")
                frame[column] = numeric


def load_sample_store() -> DataStore:
    """Load the bundled sample dataset shipped with the repo."""
    settings = get_settings()
    return DataStore.from_csv(
        settings.data_dir / "sample_budget_actuals.csv",
        settings.data_dir / "sample_transactions.csv",
        source="sample",
    )
