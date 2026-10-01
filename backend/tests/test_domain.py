from datetime import date
import pytest
from backend.domain import eligibility,add_months,score,scenarios,union_months,consistency,term_in,content_key
from backend.schemas import Criterion

def profile(**kw):
    return {'source_type':'past_applicant','matching_allowed':True,'retention_expires_at':'2027-01-01','application_status':'rejected','rejected_at':'2026-06-28',**kw}

def test_three_calendar_months_exclusive_boundary():
    assert eligibility(profile(),today=date(2026,9,27))[0]
    assert not eligibility(profile(),today=date(2026,9,28))[0]
    assert add_months(date(2026,1,31),3)==date(2026,4,30)

@pytest.mark.parametrize('status',['applied','approved','interview','hired','withdrawn'])
def test_only_rejected(status):
    assert not eligibility(profile(application_status=status),today=date(2026,7,1))[0]

def test_retention_permission_and_employee_optin():
    for change in [{'matching_allowed':False},{'suppressed':True},{'active_interview':True},{'retention_expires_at':'2026-07-01'},{'rejected_at':None}]:
        assert not eligibility(profile(**change),today=date(2026,7,1))[0]
    assert not eligibility(profile(source_type='employee',internal_visibility=False),today=date(2026,7,1))[0]
    assert not eligibility(profile(),pools=['employee'],today=date(2026,7,1))[0]

def test_dates_and_no_substring_false_match():
    assert not term_in('Java','JavaScript')
    assert term_in('Java','Built Java services')
    roles=[{'start':'2023-01','end':'2023-12'},{'start':'2023-06','end':'2024-05'}]
    assert union_months(roles)==17
    assert union_months([{'start':None,'end':'2024-01'}]) is None
    assert consistency({'roles':[{'id':'r1','title':'Developer','start':'2024-12','end':'2023-01'}]})

def fixture():
    cs=[Criterion(id='a',requirement='Java',terms=['Java'],weight=3).model_dump(),Criterion(id='b',requirement='Kafka',terms=['Kafka'],weight=1).model_dump()]
    es=[{'id':'e1','text':'Built Java services.','location':'Paragraph 1'}]
    items=[{'criterion_id':'a','status':'supported','rationale':'Applied Java','evidence_ids':['e1']},{'criterion_id':'b','status':'not_evidenced','rationale':'Unknown','evidence_ids':[]}]
    return cs,items,es

def test_score_normalization_evidence_coverage_and_no_free_categories():
    cs,items,es=fixture();a=score(cs,items,es)
    assert a['overall_score']==75
    assert a['coverage']==75
    assert a['essentials']=={'supported':1,'partial':0,'not_evidenced':1,'unmet':0}
    assert score(cs,items,es+[{'id':'e2','location':'p2','text':'Java Java Java'}])['overall_score']==75

def test_invalid_evidence_and_duplicate_results_rejected():
    cs,items,es=fixture()
    with pytest.raises(ValueError):score(cs,items+[items[0]],es)
    items[0]['evidence_ids']=['invented']
    with pytest.raises(ValueError):score(cs,items,es)

def test_scenario_exact_delta_and_immutability():
    cs,items,es=fixture();a=score(cs,items,es);s=scenarios(a,95)
    assert s['hypothetical_score']==100
    assert s['combination'][0]['criterion_id']=='b'
    assert a['overall_score']==75
    assert scenarios(a,70)['combination']==[]

def test_unknown_duration_is_not_claimed_zero_experience():
    cs,items,es=fixture();cs[0]['required_months']=36;items[0]['months']=None
    a=score(cs,items,es)
    assert a['results'][0]['status']=='not_evidenced'
    assert 'unclear' in a['results'][0]['rationale']

def test_weight_only_content_key():
    cs,_,_=fixture();key=content_key(cs);cs[0]['weight']=9
    assert content_key(cs)==key
    cs[0]['full_credit']='Must own production services'
    assert content_key(cs)!=key

def test_jd_preferred_clause_does_not_affect_other_sentences():
    from backend.intelligence import extract_jd
    cs=extract_jd('Develop Java services. Kubernetes preferred.')
    assert next(c for c in cs if c['requirement']=='Java')['essential']
    assert not next(c for c in cs if c['requirement']=='Kubernetes')['essential']
