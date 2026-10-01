import pytest
from backend.schemas import Criterion
from backend.intelligence import assess_profile
from backend.domain import score
from backend import store as db
from backend.seed import seed


@pytest.mark.parametrize('title',['Graduate Developer','Application Developer','Software Engineer','Backend Developer'])
def test_backend_duties_receive_same_duration_credit_regardless_of_title(title):
    c=Criterion(id='experience',requirement='Four years of professional backend development',category='experience',required_months=48).model_dump()
    evidence=[{'id':'e1','location':'Role 1','text':f'{title} | 2020-01 to 2023-12. Developed Java services and customer APIs with PostgreSQL throughout this employment.'}]
    facts={'roles':[{'id':'r1','title':title,'start':'2020-01','end':'2023-12','evidence_ids':['e1']}]}
    result=score([c],assess_profile({'evidence':evidence,'facts':facts},[c]),evidence,facts)
    assert result['overall_score']==100
    assert result['results'][0]['status']=='supported'


def test_skills_and_title_do_not_establish_professional_duration():
    c=Criterion(id='experience',requirement='Four years of professional backend development',category='experience',required_months=48).model_dump()
    evidence=[{'id':'e1','location':'Role 1','text':'Graduate Developer | 2020-01 to 2023-12. Skills: Java, PostgreSQL. Coursework and tutorials; professional application not described.'}]
    facts={'roles':[{'id':'r1','title':'Graduate Developer','start':'2020-01','end':'2023-12','evidence_ids':['e1']}]}
    result=score([c],assess_profile({'evidence':evidence,'facts':facts},[c]),evidence,facts)
    assert result['results'][0]['status']=='not_evidenced'
    assert 'different job title does not rule out' in result['results'][0]['rationale']


def test_recruiter_can_confirm_without_searching_historical_pool(client):
    seed()
    with db.Session.begin() as s:
        for t in db.all_of(s,'task'):db.remove(s,t['id'])
        for r in db.all_of(s,'run'):db.remove(s,r['id'])
    j=client.post('/api/jobs',json={'title':'New engineering role','description':'Develop Java services.'}).json()
    response=client.post(f"/api/jobs/{j['id']}/rubric-versions",json={'revision':j['revision'],'search_existing':False})
    assert response.status_code==200
    assert response.json()['run']['total']==0
    assert client.get(f"/api/jobs/{j['id']}/matches").json()['counts']['pending']==0


def test_samples_do_not_block_new_resume_upload(client):
    import io
    from docx import Document
    seed()
    document=Document();document.add_paragraph('Fictional upload test. Developed Java services.')
    content=io.BytesIO();document.save(content)
    response=client.post('/api/imports',data={'job_id':'job_demo_1'},files=[('files',('test.docx',content.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document'))])
    assert response.status_code==200
    assert len(response.json()['successes'])==1
    assert not response.json()['errors']


def test_old_and_new_assessments_show_one_candidate(client):
    from backend.worker import claim
    from backend.services import perform_task,update_runs,collect_matches
    seed()
    while True:
        task=claim()
        if not task:break
        perform_task(task['id'])
    update_runs()
    with db.Session.begin() as s:
        job=db.get(s,'job_demo_1')
        before=collect_matches(s,job)
        original=before[0]
        db.add(s,'assessment',{**original,'id':'ignored','prompt_version':'old-method','created_at':'2099-01-01T00:00:00'},'old_assessment')
        after=collect_matches(s,job)
        assert len(after)==len(before)
        assert next(a for a in after if a['profile_id']==original['profile_id'])['id']==original['id']
