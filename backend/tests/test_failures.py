import io
from datetime import date,timedelta
from backend import store as db
from backend.seed import seed
from backend.services import perform_task,update_runs
from backend.worker import claim

def test_malformed_document_fails_in_worker_and_preserves_other_work(client):
    job=client.post('/api/jobs',json={'title':'Backend engineer','description':'Develop Java services.','internal':True}).json()
    imported=client.post('/api/imports',data={'job_id':job['id']},files=[('files',('broken.pdf',b'not a pdf','application/pdf'))])
    assert imported.status_code==200
    task=claim();assert task['kind']=='ingest'
    perform_task(task['id']);update_runs()
    p=client.get('/api/profiles').json()[0]
    assert p['processing_status']=='failed'
    assert not p['eligible']
    assert client.get('/api/processing').json()['tasks'][0]['status']=='failed'

def test_expiry_during_queue_removes_assessment(client):
    seed()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_11')
        db.put(s,p['id'],{**p,'rejected_at':(date.today()-timedelta(days=120)).isoformat()})
    for _ in range(35):
        task=claim()
        if not task:break
        perform_task(task['id'])
    update_runs()
    result=client.get('/api/jobs/job_demo_1/matches').json()
    assert all(r['profile_id']!='profile_demo_11' for r in result['rows'])
    assert result['counts']['assessed']==25

def test_export_escapes_csv_formulas_and_html(client):
    from backend.main import cell
    assert cell('=HYPERLINK("https://example.com")').startswith("'")
    assert cell(' \t+dangerous').startswith("'")
    seed()
    with db.Session.begin() as s:
        p=db.get(s,'profile_demo_1');db.put(s,p['id'],{**p,'facts':{**p['facts'],'name':'<script>alert(1)</script>'}})
    while True:
        t=claim()
        if not t:break
        perform_task(t['id'])
    body=client.get('/api/jobs/job_demo_1/exports?format=html').text
    assert '<script>alert' not in body
    assert '&lt;script&gt;' in body
