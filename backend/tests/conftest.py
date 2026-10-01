import os
import tempfile
os.environ['JOBSCORE_DATA_DIR']=tempfile.mkdtemp(prefix='jobscore-tests-')
os.environ['JOBSCORE_MODE']='demo'
os.environ['JOBSCORE_SEED']='0'
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import store as db

@pytest.fixture(autouse=True)
def clean_db():
    db.Base.metadata.drop_all(db.engine)
    db.Base.metadata.create_all(db.engine)
    yield

@pytest.fixture
def client():
    with TestClient(app) as c:yield c
