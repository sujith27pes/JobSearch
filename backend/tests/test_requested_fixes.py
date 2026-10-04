import io
from functools import lru_cache
from datetime import date
import httpx
import pytest
from docx import Document
from backend import store as db, intelligence, services
from backend.domain import score,content_key,digest
from backend.schemas import Criterion,Extracted
from backend.seed import seed
from backend.worker import claim
from backend.insights import career_context,refresh_duration,skill_freshness
from backend.tests.test_integration import drain


@lru_cache(maxsize=32)
def document(text):
    d=Document();d.add_paragraph(text);out=io.BytesIO();d.save(out);return out.getvalue()


def upload(client,text='Fictional candidate. Developed Java services.',**fields):
    return client.post('/api/imports',data={'job_id':'job_demo_1',**fields},files=[('files',('candidate.docx',document(text),'application/vnd.openxmlformats-officedocument.wordprocessingml.document'))])


@pytest.mark.parametrize('divider',['----------','•','-','***','   *   ','======','•••'])
def test_ordinary_jd_separators_do_not_become_criteria(client,divider):
    r=client.post('/api/jobs',json={'title':'Operations officer','description':f'Coordinate operational handovers.\n{divider}\nPrepare clear daily reports.'})
    assert r.status_code==200,r.text
    assert len(r.json()['draft'])==2


def test_separator_only_jd_has_recruiter_message(client):
    r=client.post('/api/jobs',json={'title':'Operations officer','description':'----------\n***\n•'})
    assert r.status_code==422
    assert 'readable requirements' in r.json()['detail']
    assert 'validation error' not in r.text


def test_scoring_recency_is_reproducible_at_saved_date():
    c=Criterion(id='c1',requirement='Java',recency_months=12).model_dump()
    e=[{'id':'e1','text':'Built Java services until 2025-06','location':'Test'}]
    items=[{'criterion_id':'c1','status':'supported','rationale':'Dated use','evidence_ids':['e1'],'last_used':'2025-06'}]
    early=score([c],items,e,today=date(2025,7,1));late=score([c],items,e,today=date(2027,1,1))
    assert early['overall_score']==100 and late['overall_score']==0
    assert early==score([c],items,e,today=date.fromisoformat(early['evaluation_date']))
    assert early['results'][0]['status']=='supported' and late['results'][0]['status']=='unmet'


def test_offline_ongoing_dates_use_injected_today():
    c=Criterion(id='c1',requirement='Backend experience',category='experience',required_months=48).model_dump()
    e=[{'id':'e1','text':'Graduate Developer | 2021-01 to present. Developed APIs and Java services.'}]
    facts={'roles':[{'id':'r1','title':'Graduate Developer','start':'2021-01','end':'present','evidence_ids':['e1']}]}
    p={'facts':facts,'evidence':e}
    a=intelligence.assess_profile(p,[c],today=date(2025,1,1))[0]
    b=intelligence.assess_profile(p,[c],today=date(2026,1,1))[0]
    assert a['months']==49 and b['months']==61
    assert a['last_used']==b['last_used']=='present'


def test_identical_upload_reuses_identity_and_updated_file_uses_version(client):
    seed();drain()
    first=upload(client).json();assert not first['errors']
    pid=first['successes'][0]['id'];drain()
    with db.Session() as s:previous=db.get(s,pid);count=len(db.all_of(s,'profile'));tasks=len(db.all_of(s,'task'))
    same=upload(client).json()
    assert same['successes'][0]['id']==pid and same['successes'][0]['unchanged']
    with db.Session() as s:
        assert len(db.all_of(s,'profile'))==count and len(db.all_of(s,'task'))==tasks
    ambiguous=upload(client,'Fictional candidate. Developed Java and PostgreSQL services.').json()
    assert not ambiguous['successes'] and 'Replace an existing candidate' in ambiguous['errors'][0]['error']
    changed=upload(client,'Fictional candidate. Developed Java and PostgreSQL services.',profile_id=pid,profile_revision=previous['revision']).json()
    assert changed['successes'][0]['id']==pid and not changed['errors']
    drain()
    with db.Session() as s:
        current=db.get(s,pid)
        assert current['version_id']!=previous['version_id'] and len(db.all_of(s,'profile'))==count
        assert len([v for v in db.all_of(s,'profile_version') if v['profile_id']==pid])==2


def test_replace_resume_rejects_stale_revision(client):
    seed();drain();first=upload(client).json();pid=first['successes'][0]['id'];drain()
    assert upload(client,'Updated fiction.',profile_id=pid,profile_revision=0).status_code==409


def test_compare_includes_third_candidate_in_all_three_pairs(client):
    seed();drain()
    rows=client.get('/api/jobs/job_demo_1/matches').json()['rows']
    ids=[a['id'] for a in [rows[0],rows[len(rows)//2],rows[-1]]]
    data=client.post('/api/jobs/job_demo_1/comparisons',json={'assessment_ids':ids}).json()
    assert len(data['pairwise_differences'])==3
    assert {p['left_id'] for p in data['pairwise_differences']}|{p['right_id'] for p in data['pairwise_differences']}==set(ids)
    byid={a['id']:a for a in data['candidates']}
    for pair in data['pairwise_differences']:
        a,b=byid[pair['left_id']],byid[pair['right_id']]
        for diff in pair['differences']:
            left=next(r for r in a['results'] if r['criterion_id']==diff['criterion_id'])
            right=next(r for r in b['results'] if r['criterion_id']==diff['criterion_id'])
            assert diff['delta']==round(left['contribution']-right['contribution'],2)


def test_missing_profile_snapshot_is_skipped(monkeypatch):
    seed();drain();original=db.all_of
    def missing(s,kind):return [] if kind=='profile' else original(s,kind)
    monkeypatch.setattr(db,'all_of',missing)
    with db.Session() as s:assert services.collect_matches(s,db.get(s,'job_demo_1'))==[]


def test_deleting_one_profile_preserves_shared_extraction_cache(client):
    seed();drain();pid=upload(client).json()['successes'][0]['id'];drain()
    with db.Session.begin() as s:
        p=db.get(s,pid)
        sibling=db.add(s,'profile',{**p,'source_record_id':'different-source-id'},'shared_document_person')
        cache=next(c for c in db.all_of(s,'extraction_cache') if c['document_hash']==p['document_hash'])
    assert client.delete('/api/profiles/'+pid).status_code==200
    with db.Session() as s:assert db.get(s,cache['id']) and db.get(s,sibling['id'])
    assert client.delete('/api/profiles/'+sibling['id']).status_code==200
    with db.Session() as s:assert not db.get(s,cache['id'])


def test_ingest_claim_starts_in_parsing_stage(client):
    seed();drain();upload(client)
    t=claim()
    assert t['kind']=='ingest'
    with db.Session() as s:assert db.get(s,t['id'])['stage']=='parsing'


def test_deletion_removes_unshared_extractions_from_previous_versions(client):
    seed();drain();pid=upload(client).json()['successes'][0]['id'];drain()
    with db.Session() as s:p=db.get(s,pid);old_hash=p['document_hash']
    updated=upload(client,'Fictional candidate. Developed Kafka consumers.',profile_id=pid,profile_revision=p['revision']).json()
    assert not updated['errors'];drain()
    with db.Session() as s:
        new_hash=db.get(s,pid)['document_hash']
        assert len([r for r in db.all_of(s,'extraction_cache') if r['document_hash'] in (old_hash,new_hash)])==2
    assert client.delete('/api/profiles/'+pid).status_code==200
    with db.Session() as s:assert not any(r['document_hash'] in (old_hash,new_hash) for r in db.all_of(s,'extraction_cache'))


def test_career_context_is_descriptive_and_excludes_ongoing_roles():
    roles=[{'id':str(i),'title':title,'start':start,'end':end,'evidence_ids':[]} for i,(title,start,end) in enumerate([('Developer','2022-01','2022-06'),('Engineer','2023-01','2023-06'),('Lead','2024-01','2024-06'),('Director','2025-01','present')])]
    context=career_context({'facts':{'roles':roles},'evidence':[]},today=date(2026,10,1))
    assert context['repeated_short_tenures'] and len(context['short_completed_roles'])==3
    assert [r['months_between_starts'] for r in context['title_changes']]==[12,12,12]
    assert 'not verified promotions' in context['note'] and 'never change the score' in context['note']


def test_skill_freshness_dated_mention_is_not_asserted_use():
    p={'facts':{'skills':['Java']},'evidence':[{'id':'e1','text':'Coursework: Java, 2020-01','location':'Test'}]}
    row=skill_freshness(p)[0]
    assert row['last_evidenced'] is None and row['dated_mention']=='2020-01'
    assert 'use not established' in row['label']


def test_calendar_refresh_advances_only_supported_full_interval():
    facts={'roles':[{'id':'r1','start':'2025-01','end':'present'}]}
    full={'role_ids':['r1'],'months':6,'evidence_ids':['e1']};project={**full,'months':2}
    rows=refresh_duration([full,project],facts,'2025-06-01',date(2025,8,1))
    assert rows[0]['months']==8 and rows[1]['months']==2 and full['months']==6


def test_recency_refresh_reuses_model_interpretation(client,monkeypatch):
    seed();drain()
    with db.Session.begin() as s:
        j=db.get(s,'job_demo_1');r=db.get(s,j['rubric_id']);p=db.get(s,'profile_demo_1')
        criteria=[Criterion(id='c1',requirement='Java',terms=['Java'],recency_months=12).model_dump()]
        r=db.add(s,'rubric',{**r,'criteria':criteria,'version':r['version']+1})
        j=db.put(s,j['id'],{**j,'draft':criteria,'rubric_id':r['id']})
        items=[{'criterion_id':'c1','status':'supported','rationale':'Applied Java','evidence_ids':['e2'],'last_used':'2020-01'}]
        key=digest([p['version_id'],content_key(criteria),intelligence.MODE,intelligence.MODEL,intelligence.PROMPT_VERSION])
        db.add(s,'cache',{'results':items,'profile_ids':[p['id']],'evaluation_date':'2020-01-01'},'cache_'+key)
        db.add(s,'assessment',{**score(criteria,items,p['evidence'],p['facts'],today=date(2020,1,1)),'profile_id':p['id'],'profile_version':p['version_id'],'job_id':j['id'],'rubric_id':r['id'],'rubric_version':r['version'],'prompt_version':intelligence.PROMPT_VERSION,'mode':intelligence.MODE,'engine':intelligence.MODEL})
    monkeypatch.setattr(services,'assess_profile',lambda *a,**k:pytest.fail('A recency arithmetic update must not call the model'))
    services.process_refreshes()
    drain()
    rows=client.get('/api/jobs/job_demo_1/matches').json()['rows']
    a=next(a for a in rows if a['profile_id']==p['id'])
    assert a['overall_score']==0 and a['reused'] and not a['needs_reassessment']


def test_other_role_search_is_explicit_and_does_not_transfer_application(client):
    seed();drain()
    with db.Session() as s:p=db.get(s,'profile_demo_1');status=p['application_status']
    assert client.get('/api/profiles/'+p['id']+'/opportunities').json()['rows']==[]
    requested=client.post('/api/profiles/'+p['id']+'/opportunities')
    assert requested.status_code==200 and requested.json()['total']==2
    assert client.post('/api/profiles/'+p['id']+'/opportunities').status_code==422
    drain()
    data=client.get('/api/profiles/'+p['id']+'/opportunities').json()
    assert len(data['rows'])==2 and not data['pending']
    assert client.post('/api/profiles/'+p['id']+'/opportunities').json()['total']==0
    assert not any(a['profile_id']==p['id'] for a in client.get('/api/jobs/job_demo_2/matches').json()['rows'])
    with db.Session() as s:assert db.get(s,p['id'])['application_status']==status and db.get(s,p['id'])['job_id']==p['job_id']


def test_monitoring_samples_permissions_and_suppression(client,monkeypatch):
    seed();drain()
    assert client.get('/api/monitoring').json()['assessment_count']==0
    data=client.get('/api/monitoring?include_samples=true').json()
    assert data['assessment_count']==26 and 'do not measure' in data['note']
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_1');db.put(s,p['id'],{**p,'suppressed':True})
    assert client.get('/api/monitoring?include_samples=true').json()['assessment_count']==25
    import backend.main as main
    monkeypatch.setattr(main,'POOLS',['employee'])
    assert client.get('/api/profiles/profile_demo_1/opportunities').status_code==403
    assert {g['source'] for g in client.get('/api/monitoring?include_samples=true').json()['groups']}=={'employee'}


def test_nemotron_payload_uses_supported_non_streaming_mode(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','private-test-key');monkeypatch.setenv('LLM_BASE_URL','https://integrate.api.nvidia.com/v1')
    monkeypatch.setattr(intelligence,'MODEL','nvidia/nemotron-3-ultra-550b-a55b')
    captured={}
    def respond(*a,**k):
        captured.update(k['json'])
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n{"name":"Fictional person","roles":[],"skills":[]}\n```'}}],'usage':{'total_tokens':120}})
    monkeypatch.setattr(httpx.Client,'post',respond)
    assert intelligence.call_model('Extract',{},Extracted)['name']=='Fictional person'
    assert captured['stream'] is False and captured['reasoning_effort']=='none' and 'response_format' not in captured
    with db.Session() as s:assert db.all_of(s,'provider_slot')[0]['lease_until']==0


def test_truncated_model_output_is_not_saved_as_an_assessment(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','private-test-key');monkeypatch.setenv('LLM_BASE_URL','https://example.invalid/v1')
    monkeypatch.setattr(intelligence,'MODEL','test')
    monkeypatch.setattr(httpx.Client,'post',lambda *a,**k:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"name":"Fiction"}'}}]}))
    with pytest.raises(ValueError,match='output limit'):intelligence.call_model('Extract',{},Extracted)


def test_nvidia_shared_cooldown_prevents_follow_on_requests(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','private-test-key');monkeypatch.setenv('LLM_BASE_URL','https://integrate.api.nvidia.com/v1')
    monkeypatch.setattr(intelligence,'MODEL','nvidia/nemotron-3-ultra-550b-a55b')
    calls=[]
    def quota(*a,**k):
        calls.append(1)
        return httpx.Response(429,headers={'retry-after':'3600'})
    monkeypatch.setattr(httpx.Client,'post',quota)
    for _ in range(2):
        with pytest.raises(ValueError,match='429'):intelligence.call_model('Extract',{},Extracted)
    assert len(calls)==1


def test_promotion_timing_requires_explicit_dated_claims():
    p={'facts':{'roles':[]},'evidence':[{'id':'e1','text':'Promoted to Senior Engineer in 2022-01.'},{'id':'e2','text':'Promoted to Team Lead in 2024-01.'},{'id':'e3','text':'Developer since 2021-01. Promoted to engineer.'},{'id':'e4','text':'Not promoted to director in 2025-01.'}]}
    context=career_context(p,today=date(2026,10,1))
    assert len(context['documented_promotions'])==3
    assert context['documented_promotions'][-1]['date'] is None
    assert context['promotion_intervals_months']==[24]


def test_future_periods_and_future_use_do_not_receive_documented_credit():
    from backend.domain import union_months
    assert union_months([{'start':'2025-01','end':'2026-12'}],today=date(2025,6,1))==6
    assert union_months([{'start':'2026-01','end':'2026-12'}],today=date(2025,6,1)) is None
    c=Criterion(id='c1',requirement='Java',recency_months=12).model_dump()
    items=[{'criterion_id':'c1','status':'supported','rationale':'Future dated use','evidence_ids':['e1'],'last_used':'2026-01'}]
    a=score([c],items,[{'id':'e1','text':'Java use 2026-01'}],today=date(2025,6,1))
    assert a['overall_score']==0 and a['results'][0]['status']=='not_evidenced'


def test_approved_skill_alias_keeps_last_evidenced_use():
    p={'facts':{'skills':['JVM']},'evidence':[{'id':'e1','text':'Developed JVM services to present.'}]}
    rows=[{'category':'skill','requirement':'Java','terms':['Java'],'equivalents':['JVM'],'evidence_ids':['e1'],'last_used':'present'}]
    assert skill_freshness(p,rows)[0]['last_evidenced']=='present'


def test_other_jobs_can_be_selected_when_more_than_three_are_available(client):
    seed();drain()
    for n in range(2):
        j=client.post('/api/jobs',json={'title':f'Additional backend job {n}','description':'Develop Java services.'}).json()
        assert client.post('/api/jobs/'+j['id']+'/rubric-versions',json={'revision':j['revision'],'search_existing':False}).status_code==200
    data=client.get('/api/profiles/profile_demo_1/opportunities').json()
    assert len(data['available_jobs'])==4
    selected=[j['id'] for j in data['available_jobs'][-2:]]
    r=client.post('/api/profiles/profile_demo_1/opportunities',json={'job_ids':selected})
    assert r.status_code==200 and r.json()['total']==2
    drain()
    assert {a['job_id'] for a in client.get('/api/profiles/profile_demo_1/opportunities').json()['rows']}==set(selected)
