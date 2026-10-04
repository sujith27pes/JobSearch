from datetime import date, timedelta

import pytest

from backend import store as db, main
from backend.domain import add_months, eligibility
from backend.seed import seed
from backend.tests.test_integration import drain


def reject(client,pid='profile_demo_1',revision=0,**changes):
    return client.patch('/api/jobs/job_demo_1/profiles/'+pid+'/review',json={'revision':revision,'status':'rejected','reason':'Role requirements do not align with documented experience.',**changes})


def test_rejection_moves_current_applicant_into_rediscovery_for_other_jobs(client):
    seed();drain()
    before=next(p for p in client.get('/api/profiles').json() if p['id']=='profile_demo_1')
    response=reject(client)
    assert response.status_code==200,response.text
    assert response.json()['status']==response.json()['stage']=='rejected'
    with db.Session() as s:
        p=db.get(s,'profile_demo_1')
        assert p['source_type']=='past_applicant' and p['application_status']=='rejected'
        assert p['rejected_at']==date.today().isoformat() and not p['active_interview']
        assert p['rejected_job_id']=='job_demo_1'
        assert p['previous_job_title']==db.get(s,'job_demo_1')['title']
        assert p['version_id']==before['version_id'] and p['facts']==before['facts']
        assert p['matching_allowed']==before['matching_allowed']
        assert p['retention_expires_at']==before['retention_expires_at']
        assert eligibility(p,db.get(s,'job_demo_2'))[0]
        assert not eligibility(p,db.get(s,'job_demo_1'))[0]
        assert not eligibility(p,db.get(s,'job_demo_2'),today=add_months(date.today(),3))[0]
    assert all(a['profile_id']!='profile_demo_1' for a in client.get('/api/jobs/job_demo_1/matches').json()['rows'])
    response=client.post('/api/jobs/job_demo_2/match-runs')
    assert response.status_code==200,response.text
    drain()
    row=next(a for a in client.get('/api/jobs/job_demo_2/matches').json()['rows'] if a['profile_id']=='profile_demo_1')
    assert row['profile']['source_type']=='past_applicant'
    assert not any(p['profile_id']=='profile_demo_1' for p in client.get('/api/interviews').json())


def test_repeated_rejection_preserves_original_date(client):
    seed();reject(client)
    original=(date.today()-timedelta(days=10)).isoformat()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_1');db.put(s,p['id'],{**p,'rejected_at':original})
    response=reject(client,revision=1)
    assert response.status_code==200,response.text
    with db.Session() as s:assert db.get(s,'profile_demo_1')['rejected_at']==original


def test_stale_rejection_is_rejected_without_changing_profile(client):
    seed()
    client.patch('/api/jobs/job_demo_1/profiles/profile_demo_1/review',json={'revision':0,'status':'reviewing','reason':'Review in progress'})
    assert reject(client).status_code==409
    with db.Session() as s:assert db.get(s,'profile_demo_1')['source_type']=='current_applicant'


@pytest.mark.parametrize('changes',[{'reason':'   '},{'move_to_interview':True}])
def test_rejection_requires_reason_and_cannot_also_move_to_interview(client,changes):
    seed()
    assert reject(client,**changes).status_code==422
    with db.Session() as s:assert db.get(s,'profile_demo_1')['application_status']=='applied'


@pytest.mark.parametrize('pid',['profile_demo_11','profile_demo_23'])
def test_rejection_does_not_convert_past_or_employee_sources(client,pid):
    seed()
    with db.Session() as s:before=db.get(s,pid)
    assert reject(client,pid=pid).status_code==422
    with db.Session() as s:assert db.get(s,pid)==before


def test_rejection_respects_destination_pool_permission(client,monkeypatch):
    seed();monkeypatch.setattr(main,'POOLS',['current_applicant'])
    assert reject(client).status_code==403
    with db.Session() as s:assert db.get(s,'profile_demo_1')['source_type']=='current_applicant'


def test_rejection_removes_own_interview_but_preserves_other_interview_block(client):
    seed()
    for pid,interview_job in [('profile_demo_1','job_demo_1'),('profile_demo_2','job_demo_2')]:
        with db.Session.begin() as s:
            p=db.get(s,pid);db.put(s,pid,{**p,'application_status':'interview','active_interview':True,'interview_job_id':interview_job})
        assert reject(client,pid=pid).status_code==200
        with db.Session() as s:
            p=db.get(s,pid)
            assert p['active_interview']==(interview_job!='job_demo_1')
            assert eligibility(p,db.get(s,'job_demo_3'))[0]==(interview_job=='job_demo_1')


def test_rejection_invalidates_cached_detail_comparison_and_exports(client):
    seed();drain()
    rows=client.get('/api/jobs/job_demo_1/matches').json()['rows']
    rejected=next(a for a in rows if a['profile_id']=='profile_demo_1')
    other=next(a for a in rows if a['profile_id']!='profile_demo_1')
    assert reject(client).status_code==200
    assert client.get('/api/assessments/'+rejected['id']).status_code==410
    assert client.post('/api/jobs/job_demo_1/comparisons',json={'assessment_ids':[rejected['id'],other['id']]}).status_code==410
    assert 'Aarav Mehta' not in client.get('/api/jobs/job_demo_1/exports?format=csv').text


def test_resume_update_does_not_reset_local_rejection_date_or_job(client):
    import io
    from docx import Document
    seed();reject(client)
    original=(date.today()-timedelta(days=10)).isoformat()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_1');db.put(s,p['id'],{**p,'rejected_at':original})
    document=Document();document.add_paragraph('Updated fictional candidate. Developed Java services.')
    out=io.BytesIO();document.save(out)
    manifest=('source_type,source_record_id,filename,updated_at,matching_allowed,retention_expires_at,application_status,rejected_at\n'
              f'past_applicant,SYN-001,updated.docx,{date.today()},true,{date.today()+timedelta(days=90)},rejected,{date.today()}\n')
    response=client.post('/api/imports',data={'source_type':'past_applicant'},files=[('files',('updated.docx',out.getvalue())),('manifest',('metadata.csv',manifest.encode()))])
    assert response.status_code==200 and not response.json()['errors'],response.text
    drain()
    with db.Session() as s:
        p=db.get(s,'profile_demo_1')
        assert p['rejected_at']==original and p['rejected_job_id']=='job_demo_1'
        assert p['previous_job_title']==db.get(s,'job_demo_1')['title']
        assert not eligibility(p,db.get(s,'job_demo_1'))[0]
        assert eligibility(p,db.get(s,'job_demo_2'))[0]


def test_legacy_rejected_current_profile_keeps_original_clock(client):
    seed()
    original=(date.today()-timedelta(days=10)).isoformat()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_1');db.put(s,p['id'],{**p,'application_status':'rejected','rejected_at':original})
    assert reject(client).status_code==200
    with db.Session() as s:assert db.get(s,'profile_demo_1')['rejected_at']==original
