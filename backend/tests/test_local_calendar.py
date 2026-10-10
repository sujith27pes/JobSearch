from datetime import date, datetime
from backend import domain
from backend.schemas import Criterion

class LocalDay(date):
    @classmethod
    def today(cls):return cls(2026,10,9)

class PreviousUtcDay(datetime):
    @classmethod
    def now(cls,tz=None):return cls(2026,10,8,19)

def test_same_day_rejection_is_eligible_across_local_utc_midnight(monkeypatch):
    monkeypatch.setattr(domain,'date',LocalDay)
    monkeypatch.setattr(domain,'datetime',PreviousUtcDay)
    profile={'source_type':'past_applicant','matching_allowed':True,'retention_expires_at':'2027-01-01','application_status':'rejected','rejected_at':'2026-10-09'}
    assert domain.eligibility(profile)==(True,'Eligible')
    assert not domain.eligibility({**profile,'retention_expires_at':'2026-10-09'})[0]

def test_default_scoring_uses_the_same_local_evaluation_day(monkeypatch):
    monkeypatch.setattr(domain,'date',LocalDay)
    monkeypatch.setattr(domain,'datetime',PreviousUtcDay)
    c=Criterion(id='c1',requirement='Java service development').model_dump()
    item={'criterion_id':'c1','status':'supported','rationale':'Applied work.','evidence_ids':['e1']}
    assert domain.score([c],[item],[{'id':'e1','text':'Built Java services.'}])['evaluation_date']=='2026-10-09'
