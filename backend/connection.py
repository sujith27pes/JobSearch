"""Verified TLS and safe connection diagnostics; never log keys or provider bodies."""
import json
import os
import socket
import ssl
from datetime import datetime,timezone
from urllib.parse import urlsplit
from urllib.request import getproxies
import certifi
import httpx


def tls_context():
    # Windows' approved system roots include corporate HTTPS-inspection certificates.
    context=ssl.create_default_context() if os.name=='nt' else ssl.create_default_context(cafile=certifi.where())
    bundle=os.getenv('LLM_CA_BUNDLE') or os.getenv('SSL_CERT_FILE')
    directory=os.getenv('SSL_CERT_DIR')
    if bundle or directory:
        try:context.load_verify_locations(cafile=bundle or None,capath=directory or None)
        except (OSError,ssl.SSLError):
            raise ValueError('The configured CA certificate bundle cannot be loaded. Check LLM_CA_BUNDLE or SSL_CERT_FILE/SSL_CERT_DIR. Certificate verification remains required.') from None
    return context


def connection_reason(error):
    chain=[];seen=set();current=error
    while current and id(current) not in seen:
        seen.add(id(current));chain.append(current)
        current=current.__cause__ or current.__context__
    if any(isinstance(e,ssl.SSLCertVerificationError) for e in chain):
        return 'TLS certificate verification failed. Use your company-approved CA bundle through LLM_CA_BUNDLE, or ask IT to verify HTTPS inspection. Do not disable certificate verification.'
    if any(isinstance(e,socket.gaierror) for e in chain):
        return 'DNS lookup failed for the model provider. Check internet access, company DNS and VPN, then retry.'
    if any(isinstance(e,PermissionError) or getattr(e,'winerror',None)==10013 or getattr(e,'errno',None) in (13,10013) for e in chain):
        return 'Network access was denied by the operating system or execution environment. Start JobScore in your own PowerShell terminal; if it still fails, ask IT to check outbound HTTPS permissions.'
    if any(isinstance(e,httpx.ProxyError) for e in chain):
        return 'The configured proxy could not reach the model provider. Check the company proxy/VPN configuration with IT.'
    if any(isinstance(e,ConnectionRefusedError) for e in chain):
        return 'The connection was refused. Check provider availability, the endpoint port, proxy and firewall rules.'
    return 'Check network access, VPN/proxy and TLS certificates. If launched from a restricted environment, start JobScore from your own terminal.'


def endpoint_url():
    base=os.getenv('LLM_BASE_URL','').strip().rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('LLM_BASE_URL must be an API base URL such as https://integrate.api.nvidia.com/v1, without credentials or a query string.')
    if parsed.path.endswith('/chat/completions'):
        raise ValueError('LLM_BASE_URL must end at /v1; remove /chat/completions because JobScore adds it.')
    return base


def check_connection(generate=False):
    result={'checked_at':datetime.now(timezone.utc).isoformat(),'generation_test':generate,'key_present':bool(os.getenv('LLM_API_KEY')),'model':os.getenv('LLM_MODEL',''),'proxy_configured':bool(getproxies()),'tls_verification':True}
    try:
        base=endpoint_url();host=urlsplit(base).hostname;result['host']=host
        socket.getaddrinfo(host,urlsplit(base).port or (443 if base.startswith('https:') else 80))
        result['dns']='passed'
        with httpx.Client(timeout=httpx.Timeout(60 if generate else 20,connect=15),verify=tls_context()) as client:
            if generate:
                if not result['key_present'] or not result['model']:raise ValueError('Set LLM_API_KEY and LLM_MODEL before the generation test.')
                payload={'model':result['model'],'stream':False,'temperature':0,'max_tokens':64,'messages':[{'role':'user','content':'Connection test only. Return exactly the word CONNECTED.'}]}
                if host=='integrate.api.nvidia.com':payload['reasoning_effort']='none'
                response=client.post(base+'/chat/completions',headers={'Authorization':'Bearer '+os.environ['LLM_API_KEY']},json=payload)
            else:
                response=client.get(base+'/models')
        result.update({'http_status':response.status_code,'reachable':True,'tls':'passed' if base.startswith('https:') else 'not_used'})
        if generate and response.status_code==200:
            body=response.json()
            result['generation_passed']=body.get('choices',[{}])[0].get('message',{}).get('content','').strip()=='CONNECTED'
            result['tokens']=body.get('usage',{}).get('total_tokens')
            result['message']='Authenticated model generation passed.' if result['generation_passed'] else 'Provider responded, but the test reply was unexpected. No resume was sent.'
        elif generate:
            result['generation_passed']=False
            result['message']=('Provider rejected authentication; check the key.' if response.status_code in (401,403) else 'Provider quota/rate limit reached.' if response.status_code==429 else f'Provider returned HTTP {response.status_code}. Check model availability and configuration.')
        else:
            result['message']='The provider is reachable from this process. This no-generation check does not validate the API key or model quota.'
    except (httpx.TransportError,OSError) as exc:
        result.update({'reachable':False,'message':connection_reason(exc) if not isinstance(exc,httpx.TimeoutException) else 'The connection check timed out. Check provider availability and outbound network access.'})
    except ValueError as exc:
        result.update({'reachable':False,'message':str(exc)})
    return result


def print_check(generate=False):
    result=check_connection(generate)
    print(json.dumps(result,indent=2))
    return 0 if result.get('generation_passed' if generate else 'reachable') else 1
