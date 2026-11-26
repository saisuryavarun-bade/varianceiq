"""Exercise actual upload, tools and SSE orchestration with synthetic CSVs.

No external calls or API key. Exit 1 means the audit found product failures.
Scripted provider responses test wiring, not model accuracy or prompt obedience.
"""
from __future__ import annotations
import csv
from decimal import Decimal
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
import app.main as product
import app.agent as agent_module
from app.tools import dispatch_tool

FIXTURES = ROOT/'tests/fixtures/synthetic_product'
REPORT = ROOT/'docs/testing'
BA_COLS = ['period','department','account','budget','actual']
TX_COLS = ['date','period','department','account','vendor','amount','memo']
FINDINGS = []


def encode(columns, rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue()


def make(amounts, actual, budget=30000, period='2026-09'):
    ba = [dict(period=period,department='Operations',account='Contractors',budget=budget,actual=actual)]
    tx = [dict(date='2026-09-15',period=period,department='Operations',account='Contractors',
               vendor=f'Synthetic Vendor {i % 4}',amount=amount,memo='Fictional consulting invoice')
          for i,amount in enumerate(amounts)]
    return ba,tx


def upload(client, name, ba, tx, ba_cols=BA_COLS):
    folder = FIXTURES/name
    folder.mkdir(parents=True,exist_ok=True)
    budget, transactions = encode(ba_cols,ba), encode(TX_COLS,tx)
    (folder/'budget.csv').write_text(budget,encoding='utf-8')
    (folder/'transactions.csv').write_text(transactions,encoding='utf-8')
    return client.post('/api/upload',files={
        'budget_file': ('budget.csv',budget,'text/csv'),
        'transactions_file': ('transactions.csv',transactions,'text/csv')})


def record(name, passed, expected, observed, severity='none'):
    FINDINGS.append(dict(name=name,passed=bool(passed),expected=expected,observed=observed,
                         severity=severity if not passed else 'none'))


def drill(limit=25, period='2026-09'):
    return dispatch_tool('drill_down_variance',dict(period=period,department='Operations',
                         account='Contractors',limit=limit),product._store)


class Block:
    def __init__(self, **data):self.data=data
    def model_dump(self):return self.data


class ScriptedStream:
    def __init__(self, turn):self.turn=turn
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def __iter__(self):return iter(())
    def get_final_message(self):
        if self.turn == 0:
            specs=[('get_dataset_overview',{}),
                   ('query_variances',{'min_abs_variance':0}),
                   ('drill_down_variance',dict(period='2026-09',department='Operations',account='Contractors',limit=5)),
                   ('compose_executive_summary',{'investigation_complete':True})]
            return SimpleNamespace(stop_reason='tool_use',content=[
                Block(type='tool_use',id=f'test-{i}',name=name,input=args) for i,(name,args) in enumerate(specs)])
        return SimpleNamespace(stop_reason='end_turn',content=[
            Block(type='text',text='Scripted synthetic completion, not an AI-generated analysis.')])


class ScriptedMessages:
    def __init__(self):self.calls=[]
    def stream(self,**kwargs):
        self.calls.append(kwargs)
        return ScriptedStream(len(self.calls)-1)


def run():
    FIXTURES.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    with TestClient(product.app,raise_server_exceptions=False) as client:
        ba,tx=make([1000+i for i in range(40)],40780)
        r=upload(client,'reconciled_40_transactions',ba,tx)
        record('valid_upload',r.status_code==200,'HTTP 200',r.status_code)
        summary=client.get('/api/dataset')
        record('dataset_counts',summary.status_code==200 and summary.json()['transaction_count']==40,
               '40 uploaded transactions',summary.json())
        result=drill(5)
        record('truncated_totals',result.get('total_amount_exact')=='40780' and result.get('returned_amount_exact')=='5185'
               and result.get('matching_transaction_count')==40 and result.get('transaction_count')==5 and result.get('is_truncated'),
               'Full total 40780; displayed subtotal 5185; 5 of 40 rows',result)
        record('matching_actuals',result.get('reconciliation',{}).get('status')=='matched','matched',result.get('reconciliation'))
        snapshot=result['dataset_snapshot_sha256']
        record('citations_resolve_to_loaded_rows',all(
            Decimal(str(tx[x['source_row']-1]['amount']))==Decimal(x['amount_exact'])
            and x['source_id']==f"txn:{snapshot}:{x['source_row']}" for x in result['transactions']),
            'Each source reference resolves to its actual uploaded row',len(result['transactions']))
        top=dispatch_tool('query_variances',{'min_abs_variance':0},product._store)
        record('variance_arithmetic',top.get('variances',[{}])[0].get('variance_pct')=='+35.9%',
               '(40780-30000)/30000 = 35.933...%',top)
        vendors=dispatch_tool('summarize_vendor_spend',{'period':'2026-09'},product._store)
        record('vendor_aggregation',sum(v['transaction_count'] for v in vendors.get('vendors',[]))==40,
               'All 40 transactions counted across vendors',vendors)

        scripted=ScriptedMessages()
        fake_provider=SimpleNamespace(messages=scripted)
        with patch.object(product.settings,'anthropic_api_key','synthetic-local-placeholder'), \
             patch.object(agent_module,'Anthropic',return_value=fake_provider):
            stream=client.get('/api/investigate?period=2026-09')
        events=[json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
        tool_results=[e for e in events if e.get('type')=='tool_result']
        evidence=next((e['result'] for e in tool_results if e['name']=='drill_down_variance'),{})
        record('scripted_investigation_sse',stream.status_code==200 and len(tool_results)==4
               and evidence.get('total_amount_exact')=='40780' and events[-1].get('type')=='done'
               and len(scripted.calls)==2,'Real agent loop executes 4 tools and emits final/done; provider is scripted',
               {'http':stream.status_code,'event_types':[e['type'] for e in events],
                'tool_count':len(tool_results),'provider_turns':len(scripted.calls)})

        ba,tx=make([100,-20],80,100);upload(client,'credit_reversal',ba,tx)
        result=drill();record('credit_reversal',result['total_amount_exact']=='80' and result['reconciliation']['status']=='matched',
                              'Credit included; 100-20=80; matched',result)
        ba,tx=make([0.1,0.2],0.3,1);upload(client,'decimal_precision',ba,tx)
        result=drill();record('decimal_precision',result['total_amount_exact']=='0.3' and result['reconciliation']['status']=='matched',
                              '0.1+0.2 reconciles exactly with 0.3',result)
        ba,tx=make([100,50],200);upload(client,'missing_transaction',ba,tx)
        result=drill();record('missing_record_detection',result['reconciliation']['status']=='mismatch',
                              'Ledger 150 versus booked 200 => mismatch',result['reconciliation'])
        ba,tx=make([100,50],150);tx.append(dict(tx[0]));upload(client,'duplicate_transaction',ba,tx)
        result=drill();record('duplicate_changes_total',result['reconciliation']['status']=='mismatch',
                              'Duplicate changes ledger to 250 versus booked 150; mismatch, not deduplicated',result['reconciliation'])
        ba,tx=make([150],150);tx[0]['period']='2026-08';upload(client,'wrong_period',ba,tx)
        result=drill();record('wrong_period_exclusion',result['reconciliation']['status']=='insufficient_evidence',
                              'No in-period transactions => insufficient_evidence',result['reconciliation'])
        ba,tx=make([],0);upload(client,'no_transactions',ba,tx)
        result=drill();record('empty_ledger_not_verified_zero',result.get('reconciliation',{}).get('status')=='insufficient_evidence',
                              'Empty ledger is not a verified zero',result)
        ba,tx=make([500],500,0);upload(client,'zero_budget',ba,tx)
        result=dispatch_tool('query_variances',{'min_abs_variance':0},product._store)
        record('zero_budget_percentage',result.get('variances',[{}])[0].get('variance_pct')=='n/a',
               'No division-by-zero; percentage n/a',result)

        ba,tx=make([100],100,100);upload(client,'zero_variance',ba,tx)
        result=dispatch_tool('query_variances',{'min_abs_variance':0},product._store)
        direction=result.get('variances',[{}])[0].get('direction')
        record('zero_variance_direction',direction=='On budget','On budget for exactly zero variance',direction,'medium')
        result=dispatch_tool('compare_period_over_period',{'period_a':'2026-08','period_b':'2026-09'},product._store)
        record('absent_period_is_not_zero',bool(result.get('error') or result.get('note') or result.get('missing_periods')),
               'Explicit missing-period indication, not a fabricated zero actual',result,'high')

        for name,change in [
            ('nonnumeric_actual',lambda ba,tx:ba[0].update(actual='not-a-number')),
            ('missing_actual',lambda ba,tx:ba[0].update(actual='')),
            ('infinite_transaction',lambda ba,tx:tx[0].update(amount='inf')),
            ('invalid_period',lambda ba,tx:ba[0].update(period='2026-13')),
        ]:
            ba,tx=make([100],100);change(ba,tx)
            r=upload(client,name,ba,tx)
            record(name+'_rejected',r.status_code==400,'HTTP 400 for malformed financial input',
                   {'http':r.status_code,'body':r.json(),'downstream':dispatch_tool('query_variances',{'min_abs_variance':0},product._store)},'high')

        ba,tx=make([100],100)
        ba[0].pop('actual')
        before=product._store
        r=upload(client,'missing_column',ba,tx,[c for c in BA_COLS if c!='actual'])
        record('missing_column_rejected',r.status_code==400,'HTTP 400',r.json())
        record('failed_upload_is_atomic',product._store is before,'Failed upload preserves prior store',product._store is before)
        reset=client.post('/api/reset');restored=client.get('/api/dataset').json()
        record('reset_sample',reset.status_code==200 and restored['row_count']==75 and restored['transaction_count']==78,
               'Bundled sample restored after audit',restored)
        with patch.object(product.settings,'anthropic_api_key',''):
            blocked=client.get('/api/investigate')
        record('missing_model_key_handled',blocked.status_code==400,'HTTP 400 with configuration error',blocked.json())

    report=dict(date='2026-11-26',commit_under_test=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                scope='CSV upload, real tools, API and real agent SSE orchestration with scripted provider',
                live_model_tested=False,browser_ui_tested=False,external_calls=0,
                passed=sum(f['passed'] for f in FINDINGS),failed=sum(not f['passed'] for f in FINDINGS),checks=FINDINGS)
    (REPORT/'synthetic-product-results.json').write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    lines=['# Synthetic product test report','',f"Executed 26 November 2026 against the working tree based on commit `{report['commit_under_test']}` (including local fixes).",'',
           f"**{report['passed']} checks passed; {report['failed']} failed.**",'',
           'These tests upload generated CSVs through the real FastAPI endpoint, invoke the real analytical tools and exercise the real agent/SSE loop with a scripted provider. No LLM calls, participant study or browser rendering test were performed.', '',
           '| Check | Result | Severity | Expected |','|---|---|---|---|']
    for f in FINDINGS:lines.append(f"| {f['name']} | {'PASS' if f['passed'] else 'FAIL'} | {f['severity']} | {f['expected']} |")
    lines += ['', '## Reproduce', '', '```bash','python scripts/test_synthetic_product.py','```','',
              'Exit code 1 signals detected product failures. Generated fixtures are under `tests/fixtures/synthetic_product/`; full observations are in `synthetic-product-results.json`. The script runs an isolated in-process application and resets its dataset at the end. It does not connect to a deployed server.', '',
              '## Release interpretation','',
              'Passing deterministic checks establishes behavior only for these cases. Provider scripting verifies tool execution and event transport, not whether a real model selects the right tools, cites evidence correctly, resists malicious memos, or writes faithful conclusions. The original six failures are preserved in synthetic-product-before-fixes.json; consult the current results above for their status.']
    (REPORT/'synthetic-product-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['passed','failed','live_model_tested','commit_under_test']}))
    for f in FINDINGS:
        if not f['passed']:print('FAIL:',f['name'], '|', str(f['observed'])[:400])
    return report['failed']>0


if __name__=='__main__':sys.exit(run())
