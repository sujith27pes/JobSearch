from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

Source = Literal['current_applicant', 'past_applicant', 'employee']
Status = Literal['supported', 'partial', 'not_evidenced', 'unmet']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Criterion(StrictModel):
    id: str
    requirement: str = Field(min_length=2, max_length=500)
    source_passage: str = ''
    category: Literal['skill', 'responsibility', 'experience', 'qualification'] = 'skill'
    essential: bool = True
    weight: float = Field(default=1, ge=0, le=1000)
    enabled: bool = True
    full_credit: str = Field(default='Applied experience supported by a source passage.', max_length=1000)
    partial_credit: str = Field(default='Mentioned without application, or an approved related capability.', max_length=1000)
    equivalents: list[str] = []
    related: list[str] = []
    terms: list[str] = []
    compound: bool = False
    required_months: int | None = Field(default=None, ge=1, le=1200)
    recency_months: int | None = Field(default=None, ge=1, le=1200)

class JobCreate(StrictModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=10, max_length=20000)
    internal: bool = True

class RubricDraft(StrictModel):
    revision: int
    criteria: list[Criterion] = Field(min_length=1, max_length=20)
    @model_validator(mode='after')
    def unique(self):
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError('Criterion IDs must be unique')
        return self

class Approval(StrictModel):
    revision: int
    overlap_acknowledged: bool = False
    search_existing: bool = True

class Scenario(StrictModel):
    target: float = Field(default=85, ge=0, le=100)

class Comparison(StrictModel):
    assessment_ids: list[str] = Field(min_length=2, max_length=3)

class Review(StrictModel):
    revision: int
    status: Literal['not_reviewed', 'reviewing', 'shortlisted', 'reviewed_not_shortlisted']
    reason: str = Field(min_length=3, max_length=1000)
    move_to_interview: bool = False

class ProfilePatch(StrictModel):
    revision: int
    reason: str = Field(min_length=3, max_length=1000)
    suppressed: bool | None = None
    matching_allowed: bool | None = None
    application_status: Literal['applied', 'rejected', 'approved', 'interview', 'hired', 'withdrawn'] | None = None
    correction_text: str | None = Field(default=None, max_length=40000)

class Evidence(StrictModel):
    id: str
    location: str
    text: str

class Role(StrictModel):
    id: str
    title: str
    start: str | None = None
    end: str | None = None
    relevant: bool = False
    evidence_ids: list[str] = []

class Extracted(StrictModel):
    name: str
    title: str = ''
    roles: list[Role] = []
    skills: list[str] = []
    stated_months: int | None = None

class AssessmentItem(StrictModel):
    criterion_id: str
    status: Status
    rationale: str = Field(min_length=3)
    evidence_ids: list[str] = []
    months: int | None = Field(default=None, ge=0)
    last_used: str | None = None
    role_ids: list[str] = []

class ModelAssessment(StrictModel):
    results: list[AssessmentItem]
