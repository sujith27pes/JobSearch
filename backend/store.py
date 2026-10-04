"""Small transactional repository. No documents or secrets are written to logs."""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, String, Integer, JSON, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('JOBSCORE_DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
engine = create_engine(os.getenv('JOBSCORE_DATABASE_URL', 'sqlite:///' + str(DATA / 'jobscore.db')), connect_args={'check_same_thread': False, 'timeout': 30})

@event.listens_for(engine, 'connect')
def configure_sqlite(connection, _):
    if engine.dialect.name == 'sqlite':
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=30000')

class Base(DeclarativeBase):
    pass

class Record(Base):
    __tablename__ = 'records'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[dict] = mapped_column(JSON)
    __mapper_args__ = {'version_id_col': revision, 'version_id_generator': False}

Session = sessionmaker(engine, expire_on_commit=False)
Base.metadata.create_all(engine)

def now():
    return datetime.now(timezone.utc).isoformat()

def ident(prefix):
    return prefix + '_' + uuid.uuid4().hex[:12]

def add(s, kind, body, id=None):
    id = id or ident(kind)
    body = {**body, 'id': id, 'revision': 1, 'created_at': body.get('created_at', now())}
    s.add(Record(id=id, kind=kind, revision=1, body=body))
    s.flush()
    return body

def get(s, id, kind=None):
    r = s.get(Record, id)
    if not r or (kind and r.kind != kind):
        return None
    return {**r.body, 'revision': r.revision}

def all_of(s, kind):
    return [{**r.body, 'revision': r.revision} for r in s.scalars(select(Record).where(Record.kind == kind).order_by(Record.body['created_at'].as_string(), Record.id)).all()]

def put(s, id, body):
    r = s.get(Record, id)
    if not r:
        raise ValueError('Record no longer exists')
    if 'revision' in body and body['revision'] != r.revision:
        from sqlalchemy.orm.exc import StaleDataError
        raise StaleDataError('Record changed concurrently')
    r.revision += 1
    r.body = {**body, 'created_at': body.get('created_at', r.body.get('created_at', now())), 'id': id, 'revision': r.revision}
    s.flush()
    return r.body

def remove(s, id):
    r = s.get(Record, id)
    if r:
        s.delete(r)

def audit(s, action, target, reason, actor='local-recruiter'):
    return add(s, 'event', {'action': action, 'target_id': target, 'reason': reason, 'actor': actor, 'at': now()})
