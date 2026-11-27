from decimal import Decimal
import copy
import json
import httpx
from openai import OpenAI
import app.assist as assist
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app.data_loader import DataStore
from app.review import build_review
from app.assist import validate_draft, InvalidDraft
import app.main as product


def store():
    ba = pd.DataFrame([
        dict(period='2026-08',department='Ops',account='Fees',budget=100,actual=0),
        dict(period='2026-09',department='Ops',account='Fees',budget=100,actual=125),
        dict(period='2026-09',department='Sales',account='Fees',budget=200,actual=200)])
    tx = pd.DataFrame([
        dict(date='2026-09-01',period='2026-09',department='Ops',account='Fees',vendor='V',amount=100,memo='Invoice'),
        dict(date='2026-09-02',period='2026-09',department='Ops',account='Fees',vendor='V',amount=25,memo='Invoice')])
    return DataStore(ba,tx)


def test_exact_review_and_missing_not_zero():
    r=build_review(store(),'2026-09',25)
    assert r['totals']['variance_exact']=='25'
    assert r['totals']['material_count']==1
    f=r['findings'][0]
    assert f['comparison']['actual_exact']=='0' and f['comparison']['change_exact']=='125'
    assert f['evidence']['reconciliation']['status']=='matched'
    missing=r['findings'][1]
    assert missing['comparison']['status']=='missing' and missing['comparison']['change_exact'] is None
    assert missing['evidence']['reconciliation']['status']=='insufficient_evidence'


def test_review_identity_includes_both_inputs_and_policy():
    s=store(); original=build_review(s)
    assert original==build_review(s)
    assert original['review_id']!=build_review(s,min_abs_variance=10)['review_id']
    s.budget_actuals.loc[0,'budget']=101
    changed=build_review(s)
    assert original['dataset_id']!=changed['dataset_id']
    s.transactions.loc[0,'memo']='Changed'
    assert changed['dataset_id']!=build_review(s)['dataset_id']


def test_unmapped_rows_and_duplicates_not_silently_removed():
    s=store();s.transactions=pd.concat([s.transactions,s.transactions.iloc[:1]],ignore_index=True)
    s.transactions.loc[1,'department']='Unmapped'
    r=build_review(s,'2026-09')
    assert r['quality']==dict(unmapped_transaction_rows=[2],duplicate_candidate_rows=2)
    assert r['findings'][0]['evidence']['total_amount_exact']=='200'


def test_no_data_and_materiality_zero():
    r=build_review(store(),'2026-07',0)
    assert r['status']=='no_data' and r['findings']==[]
    r=build_review(store(),'2026-09',0)
    assert r['totals']['material_count']==1


@pytest.mark.parametrize('threshold',[-1,Decimal('NaN'),Decimal('Infinity'),Decimal('1e100000')])
def test_bad_threshold(threshold):
    with pytest.raises(ValueError):build_review(store(),min_abs_variance=threshold)


def test_grouping_casefold_and_negative_budget():
    s=store();s.budget_actuals.loc[0,'period']='2026-09';s.budget_actuals.loc[0,'department']='OPS'
    s.budget_actuals.loc[0,'budget']=-200
    f=build_review(s,'2026-09',0)['findings'][0]
    assert f['budget_exact']=='-100' and f['variance_percent']=='225.00'
    assert 'multiple_budget_rows' in f['flags'] and len(f['budget_source_ids'])==2


def test_decimal_sum_and_zero_budget():
    s=store();s.budget_actuals['actual']=s.budget_actuals['actual'].astype(float)
    s.budget_actuals.loc[1,'budget']=0;s.budget_actuals.loc[1,'actual']=.3
    s.transactions['amount']=[.1,.2]
    f=build_review(s,'2026-09',0)['findings'][0]
    assert f['variance_percent'] is None and 'unbudgeted_activity' in f['flags']
    assert f['evidence']['reconciliation']['status']=='matched'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(product,'_store',store())
    monkeypatch.setattr(product.settings,'openai_api_key','')
    with TestClient(product.app) as c:yield c


def test_review_requires_no_model(client,monkeypatch):
    monkeypatch.setattr(product,'investigate_finding',lambda _:pytest.fail('Unexpected AI call'))
    response=client.get('/api/review')
    assert response.status_code==200 and response.json()['status']=='ready'
    assert response.headers['cache-control']=='no-store'
    assert "script-src 'self'" in response.headers['content-security-policy']


def request_for(client):
    r=client.get('/api/review?period=2026-09&min_abs_variance=25').json()
    return dict(review_id=r['review_id'],finding_id=r['findings'][0]['id'],period='2026-09',min_abs_variance=25)


def test_optional_ai_missing_key(client):
    assert client.post('/api/review/investigate',json=request_for(client)).status_code==503
    assert client.get('/api/review').status_code==200


def test_stale_snapshot_rejected_before_model(client,monkeypatch):
    body=request_for(client)
    product._store.budget_actuals.loc[0,'actual']=10
    monkeypatch.setattr(product,'investigate_finding',lambda _:pytest.fail('Stale data sent'))
    assert client.post('/api/review/investigate',json=body).status_code==409


def test_only_selected_scope_reaches_ai(client,monkeypatch):
    monkeypatch.setattr(product.settings,'openai_api_key','test')
    seen=[]
    def fake(finding):
        seen.append(finding)
        return {'status':'unverified_draft'}
    monkeypatch.setattr(product,'investigate_finding',fake)
    body=request_for(client)
    assert client.post('/api/review/investigate',json=body).status_code==200
    assert len(seen)==1 and seen[0]['department']=='Ops'
    assert all(t['department']=='Ops' for t in seen[0]['evidence']['transactions'])
    body['finding_id']='x'*24
    assert client.post('/api/review/investigate',json=body).status_code==404


def test_ai_failure_does_not_change_review(client,monkeypatch):
    monkeypatch.setattr(product.settings,'openai_api_key','test')
    before=client.get('/api/review').json()
    def fail(_):raise InvalidDraft('bad citation')
    monkeypatch.setattr(product,'investigate_finding',fail)
    assert client.post('/api/review/investigate',json=request_for(client)).status_code==502
    assert client.get('/api/review').json()==before


def test_budget_only_upload_and_atomic_failure(client):
    csv='period,department,account,budget,actual\n2026-09,Ops,Fees,100,125\n'
    assert client.post('/api/upload',files={'budget_file':('b.csv',csv)}).status_code==200
    assert client.get('/api/review').json()['totals']['insufficient_count']==1
    before=client.get('/api/review').json()['review_id']
    assert client.post('/api/upload',files={'budget_file':('b.csv','invalid')}).status_code==400
    assert client.get('/api/review').json()['review_id']==before


def test_draft_references_must_resolve():
    f=build_review(store(),'2026-09')['findings'][0]
    draft=dict(observations=[dict(claim='Spending above budget.',source_ids=f['budget_source_ids'])],hypotheses=[],questions=[])
    checked=validate_draft(draft,f)
    assert checked['status']=='unverified_draft'
    draft['observations'][0]['source_ids']=['invented']
    with pytest.raises(InvalidDraft):validate_draft(draft,f)


def test_upload_limit(client):
    assert client.post('/api/upload',files={'budget_file':('b.csv',b'x'*(5*1024*1024+1))}).status_code==413


def test_row_limit():
    s=store()
    with pytest.raises(ValueError, match='1,000 budget rows'):
        DataStore._validate(pd.concat([s.budget_actuals]*334),s.transactions)


def test_ai_concurrency_limit(client,monkeypatch):
    monkeypatch.setattr(product.settings,'openai_api_key','test')
    product._ai_slots.acquire()
    try:
        assert client.post('/api/review/investigate',json=request_for(client)).status_code==429
    finally:product._ai_slots.release()


def test_legacy_agent_disabled_by_default(client):
    assert client.get('/api/investigate').status_code==410


def test_packet_contains_inputs_and_exact_budget_evidence():
    s=store();r=build_review(s,'2026-09',25)
    assert len(r['source_data']['budget_actuals'])==3
    assert r['findings'][0]['budget_evidence'][0]['actual']=='125'
    restored=DataStore(pd.DataFrame(r['source_data']['budget_actuals']),pd.DataFrame(r['source_data']['transactions']))
    assert build_review(restored,'2026-09',25)['totals']==r['totals']
    assert build_review(restored,'2026-09',25)['dataset_id']==r['dataset_id']


def test_scoped_draft_through_real_sdk(monkeypatch):
    finding=build_review(store(),'2026-09',25)['findings'][0]
    draft={'observations':[{'claim':'Actual exceeds budget.','source_ids':finding['budget_source_ids']}],
           'hypotheses':['A scope change is possible, but not established.'],'questions':['Was additional work approved?']}
    seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':0,'model':'gpt-4.1-mini',
            'status':'completed','output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed',
            'content':[{'type':'output_text','text':json.dumps(draft),'annotations':[]}]}]})
    sdk=OpenAI(api_key='local-test',http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(assist,'OpenAI',lambda **kwargs:sdk)
    result=assist.investigate_finding(finding)
    assert result['status']=='unverified_draft' and result['citation_check']=='references_resolve'
    assert len(seen)==1 and seen[0]['store'] is False
    assert json.loads(seen[0]['input'])==finding and seen[0]['text']['format']['strict'] is True
    assert sdk.is_closed()
