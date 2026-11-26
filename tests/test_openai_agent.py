"""Exercise the real OpenAI SDK with local SSE responses, without network calls."""
import json
import httpx
import pytest
from openai import OpenAI
from app import agent as module
from app.config import get_settings
from app.data_loader import load_sample_store


def response(output, status='completed'):
    return dict(id='resp_test', object='response', created_at=0, model='gpt-4.1-mini',
                status=status, output=output, parallel_tool_calls=True, tool_choice='auto', tools=[])


def message(text='Evidence reviewed.'):
    return dict(id='msg_test', type='message', role='assistant', status='completed',
                content=[dict(type='output_text', text=text, annotations=[])])


def run(monkeypatch, replies, iterations=3):
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        reply=replies[len(requests)-1]
        if isinstance(reply, int):
            return httpx.Response(reply, json={'error': {'message':'PRIVATE_PROVIDER_DETAIL','type':'authentication_error'}})
        events=[dict(type='response.created',response=response([], 'in_progress')),
                dict(type='response.output_item.added',output_index=0,item=message('')),
                dict(type='response.output_text.delta',item_id='msg_test',output_index=0,content_index=0,delta='Checking data.'),
                dict(type='response.completed' if reply['status']=='completed' else 'response.'+reply['status'],response=reply)]
        body=''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in events)
        return httpx.Response(200, headers={'content-type':'text/event-stream'}, text=body)
    client=OpenAI(api_key='local-test-only',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(module,'OpenAI',lambda **kwargs:client)
    monkeypatch.setattr(get_settings(),'openai_api_key','local-test-only')
    monkeypatch.setattr(get_settings(),'max_agent_iterations',iterations)
    events=list(module.VarianceAgent(load_sample_store()).investigate('2026-09'))
    assert client.is_closed()
    return events,requests


def test_tool_roundtrip_uses_real_sdk_and_preserves_call_ids(monkeypatch):
    call=dict(type='function_call',id='fc_test',call_id='call_test',name='get_dataset_overview',arguments='{}')
    events,requests=run(monkeypatch,[response([call]),response([message()])])
    assert events[-1]['type']=='done'
    assert any(e['type']=='thinking' and e['text']=='Checking data.' for e in events)
    result=next(e for e in events if e['type']=='tool_result')
    assert result['id']=='call_test' and 'error' not in result['result']
    output=next(i for i in requests[1]['input'] if i.get('type')=='function_call_output')
    assert output['call_id']=='call_test' and json.loads(output['output'])==result['result']
    assert requests[0]['store'] is False
    assert all(t['type']=='function' and 'parameters' in t and t['strict'] is False for t in requests[0]['tools'])


@pytest.mark.parametrize('arguments',['{bad','[]','null'])
def test_invalid_tool_arguments_are_returned_to_model(monkeypatch,arguments):
    call=dict(type='function_call',id='fc_test',call_id='call_test',name='get_dataset_overview',arguments=arguments)
    events,_=run(monkeypatch,[response([call]),response([message()])])
    assert 'error' in next(e['result'] for e in events if e['type']=='tool_result')
    assert events[-1]['type']=='done'


@pytest.mark.parametrize('reply',[response([], 'incomplete'),response([]),401])
def test_failed_or_empty_response_is_not_success(monkeypatch,reply):
    events,_=run(monkeypatch,[reply])
    assert events[-1]['type']=='error'
    assert not any(e['type'] in ('final','done') for e in events)
    assert 'PRIVATE_PROVIDER_DETAIL' not in json.dumps(events)


def test_turn_limit(monkeypatch):
    call=dict(type='function_call',id='fc_test',call_id='call_test',name='get_dataset_overview',arguments='{}')
    events,requests=run(monkeypatch,[response([call])],iterations=1)
    assert len(requests)==1 and events[-1]['type']=='error'
