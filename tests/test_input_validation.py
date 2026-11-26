"""Reject malformed financial data without discarding legitimate zero/credit values."""
import pandas as pd
import pytest
from app.data_loader import DataStore
from app.tools.handlers import compare_period_over_period, query_variances


def frames():
    return (pd.DataFrame([dict(period='2026-09',department='Ops',account='Fees',budget=0,actual=0)]),
            pd.DataFrame([dict(date='2026-09-01',period='2026-09',department='Ops',account='Fees',vendor='Test',amount=-10,memo='Credit')]))


@pytest.mark.parametrize('table,column,value', [
    (0,'actual','bad'),(0,'actual',None),(0,'budget',float('inf')),
    (1,'amount',float('nan')),(1,'amount',-float('inf')),
    (0,'period','2026-13'),(1,'period','2026-00'),
    (0,'department',''),(1,'account',None),
])
def test_bad_values_rejected(table,column,value):
    pair=frames();pair[table][column]=pair[table][column].astype(object)
    pair[table].loc[0,column]=value
    with pytest.raises(ValueError):DataStore._validate(*pair)


def test_zero_credit_and_numeric_strings_are_valid():
    ba,tx=frames();ba['actual']=['0'];tx['amount']=['-10.25']
    DataStore._validate(ba,tx)
    assert ba['actual'].iloc[0]==0 and tx['amount'].iloc[0]==-10.25


def test_empty_budget_rejected_but_empty_ledger_allowed():
    ba,tx=frames()
    with pytest.raises(ValueError):DataStore._validate(ba.iloc[:0],tx)
    DataStore._validate(ba,tx.iloc[:0])


def test_missing_period_distinct_from_observed_zero():
    ba,tx=frames();s=DataStore(ba,tx)
    r=compare_period_over_period(s,'2026-08','2026-09')
    assert r['missing_periods']==['2026-08'] and r['actual_a'] is None
    assert r['actual_b']=='$0' and r['delta'] is None
    same=compare_period_over_period(s,'2026-09','2026-09')
    assert same['actual_a']=='$0' and same['delta']=='$0'


def test_filter_with_no_records_does_not_make_zero_comparison():
    ba,tx=frames()
    r=compare_period_over_period(DataStore(ba,tx),'2026-09','2026-09',department='Missing')
    assert r['missing_periods']==['2026-09'] and r['delta'] is None


def test_exactly_on_budget():
    ba,tx=frames()
    r=query_variances(DataStore(ba,tx),min_abs_variance=0)
    assert r['variances'][0]['direction']=='On budget'
