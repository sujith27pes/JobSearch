"""Regression coverage for complete recruiter workflows and queue lifecycle."""
import io
from datetime import date, timedelta

from docx import Document

from backend import store as db, main, services
from backend.seed import seed
from backend.worker import claim
from backend.tests.test_integration import drain


def resume(text='Fictional Candidate\nDeveloped Java services.'):
    document=Document()
    for line in text.splitlines():document.add_paragraph(line)
    stream=io.BytesIO();document.save(stream)
    return stream.getvalue()


def create_job(client):
    return client.post('/api/jobs',json={'title':'Java engineer','description':'Develop Java services.'}).json()


def upload(client,job,content=None,name='candidate.docx',**fields):
    return client.post('/api/imports',data={'job_id':job['id'],**fields},files=[('files',(name,content if content is not None else resume()))])


def test_full_search_does_not_reuse_applicant_only_run(client):
    seed();drain()
    with db.Session.begin() as s:
        job=db.get(s,'job_demo_1');rubric=db.get(s,job['rubric_id'])
        subset=services.queue_run(s,job,rubric,profile_ids=['profile_demo_1'])
        full=services.queue_run(s,job,rubric)
        assert full['id']!=subset['id'] and full['total']==26
        assert services.queue_run(s,job,rubric)['id']==full['id']


def test_requirements_can_be_approved_while_upload_is_queued(client):
    job=create_job(client)
    assert upload(client,job).json()['successes']
    response=client.post(f"/api/jobs/{job['id']}/rubric-versions",json={'revision':job['revision'],'search_existing':False})
    assert response.status_code==200,response.text
    drain();services.process_refreshes();drain()
    assert client.get(f"/api/jobs/{job['id']}/matches").json()['counts']['assessed']==1


def test_other_job_approval_waits_in_queue(client):
    seed()
    job=create_job(client)
    response=client.post(f"/api/jobs/{job['id']}/rubric-versions",json={'revision':job['revision'],'search_existing':True})
    assert response.status_code==200,response.text
    assert response.json()['run']['total']>0
    drain()
    assert client.get('/api/stats').json()['active_runs']==0


def test_deleting_only_queued_profile_completes_run(client):
    job=create_job(client);result=upload(client,job).json()
    pid=result['successes'][0]['id']
    assert client.delete('/api/profiles/'+pid).status_code==200
    run=client.get('/api/processing/'+result['run_id']).json()
    assert run['status']=='completed' and run['total']==0
    assert client.get('/api/stats').json()['active_runs']==0


def test_deleting_one_of_many_updates_progress_denominator(client):
    seed()
    assert client.delete('/api/profiles/profile_demo_1').status_code==200
    run=client.get('/api/processing').json()['runs'][0]
    assert run['total']==25
    drain()
    run=client.get('/api/processing/'+run['id']).json()
    assert run['completed']==run['total']==25


def test_retry_immediately_reactivates_run(client):
    job=create_job(client);result=upload(client,job,b'broken','broken.pdf').json();drain()
    task=client.get('/api/processing/'+result['run_id']).json()['tasks'][0]
    assert task['status']=='failed'
    response=client.post('/api/processing/'+task['id']+'/retry')
    assert response.status_code==200
    assert response.json()['stage']=='queued'
    run=client.get('/api/processing/'+result['run_id']).json()
    assert run['status']=='running' and run['failed']==0


def test_correction_of_failed_resume_becomes_assessable(client):
    job=create_job(client)
    client.post(f"/api/jobs/{job['id']}/rubric-versions",json={'revision':job['revision'],'search_existing':False})
    result=upload(client,job,b'broken','broken.pdf').json();drain()
    pid=result['successes'][0]['id'];profile=client.get('/api/profiles').json()[0]
    response=client.patch('/api/profiles/'+pid,json={'revision':profile['revision'],'reason':'Supply corrected evidence','correction_text':'Fictional Candidate\nDeveloped Java services.'})
    assert response.status_code==200 and response.json()['eligible']
    services.process_refreshes();drain()
    assert client.get(f"/api/jobs/{job['id']}/matches").json()['counts']['assessed']==1


def manifest(source_id='source-1',permission='true',status='rejected'):
    return ('source_type,source_record_id,filename,updated_at,matching_allowed,retention_expires_at,application_status,rejected_at\n'
            f'past_applicant,{source_id},candidate.docx,{date.today()},{permission},{date.today()+timedelta(days=90)},{status},{date.today()}\n').encode()


def test_manifest_cannot_default_missing_identity_or_permission(client):
    for fields in ({'source_id':''},{'permission':''}):
        result=client.post('/api/imports',data={'source_type':'past_applicant'},files=[('files',('candidate.docx',resume())),('manifest',('manifest.csv',manifest(**fields)))])
        assert result.status_code==422
    assert client.get('/api/profiles').json()==[]


def test_invalid_manifest_status_is_reported_per_file(client):
    result=client.post('/api/imports',data={'source_type':'past_applicant'},files=[('files',('candidate.docx',resume())),('manifest',('manifest.csv',manifest(status='typo')))]).json()
    assert not result['successes'] and 'application_status' in result['errors'][0]['error']
    assert client.get('/api/profiles').json()==[]


def test_per_file_failure_rolls_back_records_and_removes_raw_file(client,monkeypatch):
    job=create_job(client);original=db.audit
    before=set((db.DATA/'uploads').glob('*'))
    def fail_first(s,action,target,reason,actor='local-recruiter'):
        if action=='profile_imported' and len(db.all_of(s,'profile'))==1:
            # Fail after both profile and task were saved for this file.
            if db.all_of(s,'profile')[0]['filename']=='bad.docx':raise RuntimeError('Injected failure')
        return original(s,action,target,reason,actor)
    monkeypatch.setattr(db,'audit',fail_first)
    result=client.post('/api/imports',data={'job_id':job['id']},files=[('files',('bad.docx',resume())),('files',('good.docx',resume('Second fiction. Developed Java services.')))]).json()
    assert len(result['errors'])==len(result['successes'])==1
    assert [p['filename'] for p in client.get('/api/profiles').json()]==['good.docx']
    assert len(set((db.DATA/'uploads').glob('*'))-before)==1
    drain()
    assert client.get('/api/processing/'+result['run_id']).json()['status']=='completed'


def test_small_sample_mean_is_withheld_by_api(client):
    seed();drain()
    monkey_profiles=['profile_demo_'+str(i) for i in range(2,31)]
    with db.Session.begin() as s:
        for pid in monkey_profiles:
            p=db.get(s,pid);db.put(s,pid,{**p,'suppressed':True})
    data=client.get('/api/monitoring?include_samples=true').json()
    assert data['assessment_count']==1 and data['trend'][0]['mean_score'] is None


def test_blank_job_title_is_rejected(client):
    response=client.post('/api/jobs',json={'title':'   ','description':'Develop Java services.'})
    assert response.status_code==422


def test_created_practice_job_is_visible_in_default_job_list(client):
    job=create_job(client)
    assert not job['synthetic']
    assert any(j['id']==job['id'] and not j['synthetic'] for j in client.get('/api/jobs').json())


def test_startup_restores_authored_jobs_and_keeps_examples(client):
    seed();job=create_job(client)
    with db.Session.begin() as s:
        db.put(s,job['id'],{**job,'synthetic':True})
    from fastapi.testclient import TestClient
    with TestClient(main.app) as restarted:
        assert not restarted.get('/api/jobs/'+job['id']).json()['synthetic']
        assert restarted.get('/api/jobs/job_demo_1').json()['synthetic']
