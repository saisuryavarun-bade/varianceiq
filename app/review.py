"""Pure, reproducible financial review. No model, network, or mutable global state."""
from __future__ import annotations
from decimal import Decimal
import hashlib
import json
import re
from app.data_loader import DataStore
from app.evidence import exact_amount, transaction_evidence

ENGINE_VERSION = '1.0.0'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def money(value):
    return format(value, 'f')


def previous_month(period):
    year, month = map(int, period.split('-'))
    return f'{year-1:04d}-12' if month == 1 else f'{year:04d}-{month-1:02d}'


def build_review(store: DataStore, period: str | None = None, min_abs_variance=Decimal('1000')):
    threshold = exact_amount(min_abs_variance)
    if threshold < 0 or threshold > Decimal('1e18'):
        raise ValueError('Materiality must be between zero and 1e18.')
    if period and not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', period):
        raise ValueError('Period must be YYYY-MM.')
    frames = [store.budget_actuals, store.transactions]
    # Export the complete loaded input, including out-of-scope periods needed for comparison.
    # Financial values are strings so JSON number conversion cannot round them further.
    source_data = {}
    for name, frame, amounts in zip(('budget_actuals', 'transactions'), frames, (('budget','actual'), ('amount',))):
        records = frame.astype(object).where(frame.notna(), None).to_dict('records')
        source_data[name] = [{k: money(exact_amount(v)) if k in amounts else (str(v) if v is not None else None)
                              for k, v in row.items()} for row in records]
    dataset_id = digest(source_data)
    policy = dict(period=period, min_abs_variance=money(threshold), evidence_limit=25)
    review_id = digest([ENGINE_VERSION, dataset_id, policy])
    groups = {}
    for position, row in enumerate(store.budget_actuals.to_dict('records'), 1):
        key = (row['period'], row['department'].casefold(), row['account'].casefold())
        group = groups.setdefault(key, dict(period=row['period'], department=row['department'], account=row['account'],
                                            budget=Decimal(0), actual=Decimal(0), source_rows=[]))
        group['budget'] += exact_amount(row['budget'])
        group['actual'] += exact_amount(row['actual'])
        group['source_rows'].append(position)
    findings = []
    for key, group in groups.items():
        if period and key[0] != period:
            continue
        budget, actual = group['budget'], group['actual']
        variance = actual-budget
        evidence = transaction_evidence(store, group['period'], group['department'], group['account'], 25)
        previous = previous_month(group['period'])
        prior = groups.get((previous, key[1], key[2]))
        comparison = dict(period=previous, status='available' if prior else 'missing',
                          actual_exact=money(prior['actual']) if prior else None,
                          change_exact=money(actual-prior['actual']) if prior else None)
        flags = []
        if evidence['reconciliation']['status'] != 'matched':
            flags.append(evidence['reconciliation']['status'])
        if prior is None:
            flags.append('missing_prior_period')
        if len(group['source_rows']) > 1:
            flags.append('multiple_budget_rows')
        if budget == 0 and actual != 0:
            flags.append('unbudgeted_activity')
        material = variance != 0 and abs(variance) >= threshold
        direction = 'above_budget' if variance > 0 else 'below_budget' if variance < 0 else 'on_budget'
        findings.append(dict(
            id=digest([dataset_id, key])[:24], period=group['period'], department=group['department'], account=group['account'],
            budget_exact=money(budget), actual_exact=money(actual), variance_exact=money(variance),
            variance_percent=money(variance/abs(budget)*100) if budget else None,
            direction=direction, material=material, flags=flags, comparison=comparison,
            budget_source_ids=[f'budget:{dataset_id}:{n}' for n in group['source_rows']],
            budget_evidence=[dict(source_id=f'budget:{dataset_id}:{n}', source_row=n,
                                 **source_data['budget_actuals'][n-1]) for n in group['source_rows']],
            evidence=evidence,
            conclusion='Calculated variance; business cause not established.',
        ))
    findings.sort(key=lambda f: (-int(f['material']), -abs(Decimal(f['variance_exact'])), f['period'], f['department'], f['account']))
    selected_groups = {key for key in groups if not period or key[0] == period}
    orphan_rows = [i for i, row in enumerate(store.transactions.to_dict('records'), 1)
                   if (not period or row['period'] == period)
                   and (row['period'], row['department'].casefold(), row['account'].casefold()) not in selected_groups]
    selected_tx = store.transactions if not period else store.transactions[store.transactions['period'].eq(period)]
    duplicates = int(selected_tx.duplicated(keep=False).sum())
    totals = {field+'_exact': money(sum((Decimal(f[field+'_exact']) for f in findings), Decimal(0)))
              for field in ('budget', 'actual', 'variance')}
    totals.update(group_count=len(findings), material_count=sum(f['material'] for f in findings),
                  matched_count=sum(f['evidence']['reconciliation']['status']=='matched' for f in findings),
                  mismatch_count=sum(f['evidence']['reconciliation']['status']=='mismatch' for f in findings),
                  insufficient_count=sum(f['evidence']['reconciliation']['status']=='insufficient_evidence' for f in findings))
    return dict(schema_version=1, engine_version=ENGINE_VERSION, review_id=review_id, dataset_id=dataset_id,
                policy=policy, source=store.source, source_data=source_data,
                available_periods=sorted(store.budget_actuals['period'].unique().tolist()),
                status='ready' if findings else 'no_data', totals=totals, findings=findings,
                quality=dict(unmapped_transaction_rows=orphan_rows, duplicate_candidate_rows=duplicates),
                methodology=[
                    'Variance = actual minus budget. Above/below budget is neutral; revenue and expense favorability require account classification.',
                    'Materiality uses absolute variance >= the selected threshold, excluding zero variance.',
                    'Groups match department and account without case sensitivity. Multiple budget rows are summed and flagged.',
                    'Prior period is the immediately preceding calendar month for the same department and account. Missing is not zero.',
                    'Reconciliation compares all loaded matching transactions to booked actuals; displayed evidence is limited to 25 rows.',
                    'Duplicate candidates are identical rows, not confirmed duplicate payments. No rows are removed.',
                    'Totals may combine revenue and expenses; they are not profit or net income. Currency is not inferred or converted.',
                    'Decimal arithmetic uses loaded values. Source parsing may have lost precision. A matched ledger does not establish completeness or cause.',
                ])
