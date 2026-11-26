"""Tool schemas exposed to OpenAI via the native tool-use API."""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "get_dataset_overview",
        "description": (
            "Return a high-level summary of the loaded budget-vs-actuals dataset: "
            "row count, period range, list of departments, list of GL accounts, and "
            "total budgeted vs actual amounts. Always call this first."
        ),
        "type": "function",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "query_variances",
        "description": (
            "Query the budget-vs-actuals dataset for variances. Variance = actual - budget "
            "(positive means over budget on expenses / under on revenue). Returns rows "
            "sorted by absolute variance descending. Use this to identify material variances "
            "to investigate."
        ),
        "type": "function",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": (
                        "Optional period filter, e.g. '2024-Q3', '2024-10', or 'YTD'. "
                        "Omit to query all periods."
                    ),
                },
                "department": {
                    "type": "string",
                    "description": "Optional department filter, e.g. 'Marketing'.",
                },
                "account": {
                    "type": "string",
                    "description": "Optional GL account filter, e.g. 'Travel & Entertainment'.",
                },
                "min_abs_variance": {
                    "type": "number",
                    "description": (
                        "Minimum absolute variance in dollars to include. Default 50000."
                    ),
                },
                "min_abs_variance_pct": {
                    "type": "number",
                    "description": (
                        "Minimum absolute variance as a fraction (e.g. 0.15 = 15%). "
                        "Default 0.15."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows to return. Default 20.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "drill_down_variance",
        "description": (
            "Inspect transaction-level detail for a specific (period, department, account) "
            "combination. Returns the underlying journal-entry-level transactions, including "
            "vendor, exact decimal amount, date, memo and snapshot-scoped source IDs. "
            "Full matching totals are separate from returned-row subtotals; check "
            "is_truncated and reconciliation before drawing conclusions. A matched "
            "sum does not establish a causal driver."
        ),
        "type": "function",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Period in 'YYYY-MM' format, e.g. '2024-10'.",
                },
                "department": {
                    "type": "string",
                    "description": "Exact department name.",
                },
                "account": {
                    "type": "string",
                    "description": "Exact GL account name.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max transactions to return. Default 25.",
                },
            },
            "required": ["period", "department", "account"],
        },
    },
    {
        "name": "summarize_vendor_spend",
        "description": (
            "Aggregate transaction spend by vendor for a given period and optional "
            "department/account filter. Returns top vendors by spend. Useful for identifying "
            "concentration risk or one-off vendor spend."
        ),
        "type": "function",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Period in 'YYYY-MM' format or 'YTD'.",
                },
                "department": {"type": "string"},
                "account": {"type": "string"},
                "limit": {"type": "integer", "description": "Default 10."},
            },
            "required": ["period"],
        },
    },
    {
        "name": "compare_period_over_period",
        "description": (
            "Compare actuals between two periods for the same department/account. "
            "Useful for distinguishing a one-time event from a structural trend."
        ),
        "type": "function",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "period_a": {"type": "string", "description": "e.g. '2024-09'"},
                "period_b": {"type": "string", "description": "e.g. '2024-10'"},
                "department": {"type": "string"},
                "account": {"type": "string"},
            },
            "required": ["period_a", "period_b"],
        },
    },
    {
        "name": "compose_executive_summary",
        "description": (
            "Signal that you have completed your investigation and are ready to write the "
            "executive summary. Calling this tool returns a checklist of what the summary "
            "should include. Always call this BEFORE writing your final markdown summary."
        ),
        "type": "function",
        "strict": False,
        "parameters": {
            "type": "object",
            "properties": {
                "investigation_complete": {
                    "type": "boolean",
                    "description": "Set to true to confirm investigation is complete.",
                },
            },
            "required": ["investigation_complete"],
        },
    },
]
