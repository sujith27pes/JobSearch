from datetime import date
import pytest
from backend.domain import score
from backend.schemas import Criterion

TODAY=date(2026,10,9)

def inputs():
    criterion=Criterion(id='backend',requirement='Four years of backend delivery',category='experience',required_months=48).model_dump()
    evidence=[{'id':'e1','text':'January 2024 - Present: Built backend HTTP APIs and database integrations.','location':'Paragraph 4'}]
    facts={'roles':[{'id':'r1','title':'Software Engineer','start':'2024-01','end':'present','evidence_ids':['e1']}]}
    item={'criterion_id':'backend','status':'partial','rationale':'An erroneous model estimate of 21 months.','evidence_ids':['e1'],'role_ids':['r1'],'months':21,'duration_basis':'role_intervals'}
    return criterion,evidence,facts,item

def test_full_role_duration_replaces_model_arithmetic_and_explanation():
    c,e,f,i=inputs()
    result=score([c],[i],e,f,today=TODAY)
    row=result['results'][0]
    assert row['months']==34
    assert result['overall_score']==71
    assert '34 non-overlapping months' in row['rationale'] and '21' not in row['rationale']
    assert i['months']==21

def test_overlapping_role_periods_are_not_double_counted():
    c,e,f,i=inputs()
    f['roles'].append({'id':'r2','title':'Concurrent backend assignment','start':'2025-01','end':'2025-12','evidence_ids':['e1']})
    i['role_ids'].append('r2')
    assert score([c],[i],e,f,today=TODAY)['results'][0]['months']==34

def test_shorter_project_estimate_is_preserved():
    c,e,f,i=inputs();i['duration_basis']='project_estimate';i['months']=6
    result=score([c],[i],e,f,today=TODAY)
    assert result['results'][0]['months']==6 and result['overall_score']==13

@pytest.mark.parametrize('change',[{'start':None},{'evidence_ids':[]},{'start':'2027-01'},{'end':'2023-01'}])
def test_incomplete_or_ungrounded_role_duration_needs_clarification(change):
    c,e,f,i=inputs();f['roles'][0].update(change)
    result=score([c],[i],e,f,today=TODAY)
    assert result['results'][0]['months'] is None
    assert result['results'][0]['status']=='not_evidenced' and result['overall_score']==0

def test_skill_duration_cannot_use_full_job_tenure():
    c,e,f,i=inputs();c['category']='skill'
    with pytest.raises(ValueError,match='skill-specific duration'):
        score([c],[i],e,f,today=TODAY)
