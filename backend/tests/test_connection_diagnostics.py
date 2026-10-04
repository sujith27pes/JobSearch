import socket
import ssl
import httpx
import pytest
from backend.connection import connection_reason,tls_context,check_connection,endpoint_url
from backend.seed import seed
from backend import store as db
from backend.tests.test_integration import drain


@pytest.mark.parametrize('cause,expected',[(socket.gaierror(-2,'private network string'),'DNS lookup'),(ssl.SSLCertVerificationError(1,'private certificate details'),'TLS certificate'),(PermissionError(13,'private context'),'Network access was denied'),(ConnectionRefusedError(111,'private context'),'connection was refused')])
def test_connection_errors_identify_cause_without_leaking_details(cause,expected):
    e=httpx.ConnectError('private provider data');e.__cause__=cause
    message=connection_reason(e)
    assert expected in message and 'private' not in message


def test_tls_verification_is_always_enabled():
    context=tls_context()
    assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname


def test_invalid_ca_bundle_is_a_safe_configuration_error(monkeypatch):
    monkeypatch.setenv('LLM_CA_BUNDLE','missing-private-path.pem')
    with pytest.raises(ValueError,match='CA certificate bundle') as result:tls_context()
    assert 'missing-private-path' not in str(result.value)


def test_no_generation_connection_check_does_not_send_credentials(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL','https://example.invalid/v1');monkeypatch.setenv('LLM_API_KEY','test-private-key')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a:[(2,1,6,'',('127.0.0.1',443))])
    def response(self,url,**kwargs):
        assert url.endswith('/models') and not kwargs.get('headers')
        return httpx.Response(200,json={'data':[]})
    monkeypatch.setattr(httpx.Client,'get',response)
    result=check_connection()
    assert result['reachable'] and not result['generation_test']
    assert 'does not validate' in result['message'] and 'test-private-key' not in str(result)


@pytest.mark.parametrize('url',['https://example.invalid/v1/chat/completions','https://user:private@example.invalid/v1','https://example.invalid/v1?key=private'])
def test_malformed_base_url_has_no_secret_in_error(monkeypatch,url):
    monkeypatch.setenv('LLM_BASE_URL',url)
    with pytest.raises(ValueError) as result:endpoint_url()
    assert 'private' not in str(result.value)


def test_activity_marks_older_failed_attempts_as_history(client):
    seed();drain()
    with db.Session.begin() as s:
        t=next(t for t in db.all_of(s,'task') if t['profile_id']=='profile_demo_1')
        old=db.add(s,'task',{**t,'status':'failed','created_at':'2020-01-01T00:00:00','error':'Old connection error'},'old_connection_failure')
    data=client.get('/api/processing').json()
    assert next(x for x in data['tasks'] if x['id']==old['id'])['is_current'] is False
    assert next(x for x in data['tasks'] if x['id']==t['id'])['is_current'] is True
    assert client.post('/api/processing/'+old['id']+'/retry').status_code==409


def test_api_connection_check_sends_no_model_request(client,monkeypatch):
    import backend.connection as connection
    monkeypatch.setattr(connection,'check_connection',lambda:{'reachable':True,'generation_test':False,'message':'Provider reachable'})
    assert client.post('/api/model-connection/check').json()['generation_test'] is False
