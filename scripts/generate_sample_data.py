"""
Generate realistic synthetic Budget vs Actuals + transaction data for
fictional "Lumera Health" (Series-C SaaS), Q3 2025.

Deliberately plants variance patterns an agent should discover:
  * Engineering salaries underspend (unfilled reqs)
  * Engineering contractors overspend (backfill — offsetting)
  * Paid Search Non-Brand overspend (bid expansion)
  * Legal one-time settlement in August
  * Sales commissions over budget (revenue beat)
  * AWS hosting scaling with usage

Outputs:
  data/sample_budget_actuals.csv
  data/sample_transactions.csv
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

random.seed(42)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MONTHS = ["2025-07", "2025-08", "2025-09"]
MONTH_DAYS = {"2025-07": 31, "2025-08": 31, "2025-09": 30}


@dataclass
class Account:
    department: str
    account: str
    monthly_budget: float
    actual_pattern: tuple  # multiplier per month
    notes: str = ""


ACCOUNTS = [
    Account("Revenue", "Subscription Revenue", 1_800_000, (1.02, 1.05, 1.11),
            "Strong Q3 beat"),
    Account("Revenue", "Professional Services", 220_000, (0.97, 1.01, 1.03)),
    Account("Engineering", "AWS Hosting", 145_000, (1.08, 1.14, 1.22),
            "Costs scaling with usage"),
    Account("Engineering", "Snowflake Compute", 38_000, (1.05, 1.12, 1.19)),
    Account("Customer Success", "Support Tooling", 18_000, (0.98, 1.02, 1.01)),
    Account("Sales", "Sales Salaries", 420_000, (1.00, 1.00, 1.01)),
    Account("Sales", "Sales Commissions", 180_000, (1.04, 1.09, 1.18),
            "Commissions track revenue beat"),
    Account("Sales", "Sales Travel & Entertainment", 45_000, (1.12, 0.94, 1.03)),
    Account("Marketing", "Marketing Salaries", 175_000, (1.00, 1.00, 1.00)),
    Account("Marketing", "Paid Search - Brand", 35_000, (1.02, 1.04, 0.98)),
    Account("Marketing", "Paid Search - Non-Brand", 85_000, (1.32, 1.58, 1.71),
            "Aggressive bid expansion"),
    Account("Marketing", "Content & SEO", 42_000, (0.94, 0.96, 0.98)),
    Account("Marketing", "Conferences & Events", 65_000, (0.85, 1.45, 0.92),
            "Aug: HIMSS moved from Q4"),
    Account("Marketing", "Martech Subscriptions", 22_000, (1.05, 1.04, 1.06)),
    Account("Engineering", "Engineering Salaries", 780_000, (0.94, 0.91, 0.88),
            "4 senior reqs unfilled"),
    Account("Engineering", "Engineering Contractors", 85_000, (1.18, 1.34, 1.41),
            "Contractor backfill for open FTE"),
    Account("Engineering", "Developer Tools & Licenses", 45_000, (1.02, 1.06, 1.05)),
    Account("Engineering", "QA & SRE Salaries", 165_000, (0.99, 1.00, 1.01)),
    Account("G&A", "G&A Salaries", 195_000, (1.00, 1.01, 1.00)),
    Account("G&A", "Legal Fees", 28_000, (0.95, 3.20, 1.10),
            "Aug: vendor dispute settlement"),
    Account("G&A", "Audit & Accounting", 22_000, (1.00, 1.00, 1.05)),
    Account("G&A", "Rent & Utilities", 55_000, (1.00, 1.00, 1.00)),
    Account("G&A", "Insurance Premiums", 18_000, (1.00, 1.00, 1.04)),
    Account("Customer Success", "CS Salaries", 215_000, (1.00, 1.01, 1.02)),
    Account("Customer Success", "CS Tooling", 15_000, (1.03, 1.05, 1.08)),
]


def jitter(v, scale=0.005):
    return v * (1 + random.uniform(-scale, scale))


def write_budget_actuals():
    path = OUTPUT_DIR / "sample_budget_actuals.csv"
    rows = []
    for acct in ACCOUNTS:
        for month, mult in zip(MONTHS, acct.actual_pattern):
            rows.append({
                "period": month,
                "department": acct.department,
                "account": acct.account,
                "budget": round(acct.monthly_budget, 2),
                "actual": round(jitter(acct.monthly_budget * mult), 2),
            })
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["period", "department", "account", "budget", "actual"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


def write_transactions():
    path = OUTPUT_DIR / "sample_transactions.csv"
    rows = []

    drill = {
        "Paid Search - Non-Brand": [
            ("Google Ads - Generic Keywords", 0.62, "Campaign: generic health SaaS terms"),
            ("Google Ads - Competitor Keywords", 0.21, "Campaign: competitor conquest"),
            ("Bing Ads", 0.08, "Campaign: cross-platform"),
            ("Reddit Ads", 0.05, "Campaign: r/healthtech sponsored"),
            ("LinkedIn Ads", 0.04, "Campaign: decision-maker targeting"),
        ],
        "Legal Fees": [
            ("Wilson Sonsini", 0.05, "General counsel retainer"),
            ("Cooley LLP", 0.88, "Vendor dispute settlement"),
            ("USPTO", 0.04, "Trademark filing"),
            ("Fisher Phillips", 0.03, "Employment law consultation"),
        ],
        "Engineering Contractors": [
            ("Toptal - Sr Backend Dev", 0.41, "Backfill for Req #ENG-204"),
            ("Andela - Sr ML Engineer", 0.34, "Backfill for Req #ENG-211"),
            ("Independent - Frontend", 0.18, "React migration sprint"),
            ("NCC Group", 0.07, "SOC 2 renewal audit"),
        ],
        "AWS Hosting": [
            ("AWS EC2 Compute", 0.42, "us-east-1 production cluster"),
            ("AWS RDS Postgres", 0.21, "Primary database"),
            ("AWS S3 Storage", 0.11, "Object storage + backups"),
            ("AWS Data Transfer", 0.14, "Egress charges"),
            ("AWS Other", 0.12, "Lambda, CloudWatch, misc"),
        ],
        "Sales Commissions": [
            ("Q3 Commissions - Enterprise", 0.55, "Enterprise segment payout"),
            ("Q3 Commissions - Mid-Market", 0.27, "Mid-market segment payout"),
            ("Q3 Commissions - SMB", 0.11, "SMB segment payout"),
            ("Q3 SPIFFs & Accelerators", 0.07, "Quota attainment accelerators"),
        ],
        "Conferences & Events": [
            ("HIMSS 2025", 0.71, "Sponsorship booth + travel (moved from Q4)"),
            ("ViVE Healthcare Conf", 0.12, "Registration + travel"),
            ("HLTH Conference", 0.10, "Registration"),
            ("Local Meetups", 0.07, "Dinners and community events"),
        ],
    }

    actual_lookup = {}
    for acct in ACCOUNTS:
        for month, mult in zip(MONTHS, acct.actual_pattern):
            actual_lookup[(acct.account, month)] = jitter(acct.monthly_budget * mult)

    acct_dept = {a.account: a.department for a in ACCOUNTS}

    for account_name, vendors in drill.items():
        dept = acct_dept[account_name]
        for month in MONTHS:
            month_total = actual_lookup[(account_name, month)]
            days = MONTH_DAYS[month]
            for vendor, share, memo in vendors:
                day = random.randint(1, days)
                date = f"{month}-{day:02d}"
                amount = round(jitter(month_total * share, scale=0.02), 2)
                rows.append({
                    "date": date,
                    "period": month,
                    "department": dept,
                    "account": account_name,
                    "vendor": vendor,
                    "amount": amount,
                    "memo": memo,
                })

    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "period", "department", "account", "vendor", "amount", "memo"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    write_budget_actuals()
    write_transactions()
