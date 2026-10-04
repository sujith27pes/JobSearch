from fastapi.testclient import TestClient
from backend import store as db, main
from backend.cleanup_samples import remove_samples
from backend.seed import seed
from backend.tests.test_integration import drain


def test_cleanup_preserves_authored_job_uploaded_resume_and_shared_cache(client):
    seed();drain()
    job=client.post('/api/jobs',json={'title':'Authored role','description':'Develop Java services.'}).json()
    with db.Session.begin() as s:
        sample=db.get(s,'profile_demo_1')
        real=db.add(s,'profile',{**sample,'synthetic':False,'source_record_id':'uploaded-record','job_id':job['id'],'version_id':'uploaded_version'})
        db.add(s,'profile_version',{'profile_id':real['id'],'document_hash':real['document_hash']},'uploaded_version')
        shared=db.add(s,'cache',{'profile_ids':[sample['id'],real['id']],'profile_version':sample['version_id']})
        extraction=db.add(s,'extraction_cache',{'document_hash':real['document_hash']})
        db.put(s,job['id'],{**job,'synthetic':True})
    removed=remove_samples()
    assert removed['profile']==30 and removed['job']==3
    with db.Session() as s:
        assert [j['id'] for j in db.all_of(s,'job')]==[job['id']]
        assert not db.get(s,job['id'])['synthetic']
        assert [p['id'] for p in db.all_of(s,'profile')]==[real['id']]
        assert db.get(s,shared['id'])['profile_ids']==[real['id']]
        assert db.get(s,extraction['id'])
    assert remove_samples()=={}


def test_startup_never_automatically_seeds_samples(monkeypatch):
    monkeypatch.setenv('JOBSCORE_SEED','1')
    with TestClient(main.app) as client:
        assert client.get('/api/jobs').json()==[]
        assert client.get('/api/profiles').json()==[]


def test_cleanup_protects_uploaded_resume_attached_to_sample_job(client):
    seed()
    with db.Session.begin() as s:
        sample=db.get(s,'profile_demo_1')
        db.add(s,'profile',{**sample,'synthetic':False,'source_record_id':'uploaded-record'})
    import pytest
    with pytest.raises(ValueError,match='uploaded resume'):remove_samples()
    assert len(client.get('/api/profiles').json())==31
    assert len(client.get('/api/jobs').json())==3
