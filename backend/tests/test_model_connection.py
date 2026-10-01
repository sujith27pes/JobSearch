import httpx
import pytest
from backend import intelligence
from backend.schemas import Extracted


@pytest.mark.parametrize('error,message', [
    (httpx.ConnectError('private transport details'), 'Cannot connect to the model provider'),
    (httpx.ReadTimeout('private transport details'), 'Model request timed out'),
])
def test_transport_errors_are_distinct_bounded_and_safe(monkeypatch, error, message):
    monkeypatch.setenv('LLM_API_KEY', 'test-secret')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setattr(intelligence, 'MODEL', 'test-model')
    monkeypatch.setattr(intelligence.time, 'sleep', lambda _: None)
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr(httpx.Client, 'post', fail)
    with pytest.raises(ValueError, match=message) as result:
        intelligence.call_model('Extract facts', {}, Extracted)
    assert len(calls) == 3
    assert 'private transport details' not in str(result.value)
    assert 'test-secret' not in str(result.value)


def test_rate_limit_respects_retry_after(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','test-secret')
    monkeypatch.setenv('LLM_BASE_URL','https://example.invalid/v1')
    monkeypatch.setattr(intelligence,'MODEL','test-model')
    waits=[]
    monkeypatch.setattr(intelligence.time,'sleep',waits.append)
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k: httpx.Response(429,headers={'retry-after':'12'}))
    with pytest.raises(ValueError,match='rate or quota limit'):
        intelligence.call_model('Extract',{},Extracted)
    assert waits==[12,12]
