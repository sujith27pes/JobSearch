from backend.seed import seed
from backend import store as db


def test_interview_move_remains_visible_after_rediscovery_removal(client):
    seed()
    response=client.patch('/api/jobs/job_demo_1/profiles/profile_demo_11/review',json={'revision':0,'status':'reviewing','reason':'Relevant payments experience; interview next.','move_to_interview':True})
    assert response.status_code==200
    assert response.json()['stage']=='interview'
    assert response.json()['status']=='shortlisted'
    row=next(p for p in client.get('/api/interviews').json() if p['profile_id']=='profile_demo_11')
    assert row['job_id']=='job_demo_1'
    assert row['moved_at']
    assert row['reason']=='Relevant payments experience; interview next.'
    assert not next(p for p in client.get('/api/profiles').json() if p['id']=='profile_demo_11')['eligible']
    assert not any(a['profile_id']=='profile_demo_11' for a in client.get('/api/jobs/job_demo_1/matches').json()['rows'])


def test_legacy_move_visible_without_changing_saved_data(client):
    seed()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_11')
        db.put(s,p['id'],{**p,'active_interview':True,'application_status':'interview'})
        db.add(s,'review',{'job_id':'job_demo_1','profile_id':p['id'],'status':'reviewing','reason':'Legacy move','actor':'local-recruiter'})
        db.audit(s,'moved_to_interview',p['id'],'Legacy move')
    row=next(p for p in client.get('/api/interviews').json() if p['profile_id']=='profile_demo_11')
    assert row['job_id']=='job_demo_1'
    assert row['reason']=='Legacy move'
    assert row['moved_at']


def test_interviews_respect_retention_and_pool_permissions(client,monkeypatch):
    seed()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_20')
        db.put(s,p['id'],{**p,'retention_expires_at':'2020-01-01'})
    assert not any(p['profile_id']=='profile_demo_20' for p in client.get('/api/interviews').json())
    import backend.main as main
    monkeypatch.setattr(main,'POOLS',['employee'])
    assert client.get('/api/interviews').json()==[]


def test_resume_refresh_keeps_interview_tracking(client):
    import io
    from datetime import date,timedelta
    from docx import Document
    seed()
    client.patch('/api/jobs/job_demo_1/profiles/profile_demo_1/review',json={'revision':0,'status':'reviewing','reason':'Proceed with interview','move_to_interview':True})
    document=Document();document.add_paragraph('Updated fictional resume. Developed Java services.')
    content=io.BytesIO();document.save(content)
    today=date.today()
    manifest=('source_type,source_record_id,filename,updated_at,matching_allowed,retention_expires_at\n'
              f'current_applicant,SYN-001,updated.docx,{today},true,{today+timedelta(days=90)}\n')
    response=client.post('/api/imports',data={'job_id':'job_demo_1'},files=[('files',('updated.docx',content.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),('manifest',('metadata.csv',manifest.encode(),'text/csv'))])
    assert response.status_code==200
    assert not response.json()['errors']
    row=next(p for p in client.get('/api/interviews').json() if p['profile_id']=='profile_demo_1')
    assert row['job_id']=='job_demo_1'
    assert row['name']=='Aarav Mehta'
    assert row['reason']=='Proceed with interview'
