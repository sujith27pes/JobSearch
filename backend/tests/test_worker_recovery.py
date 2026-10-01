from concurrent.futures import Future
from backend import worker, store as db


def isolate_tick(monkeypatch):
    monkeypatch.setattr(worker, 'claim', lambda: None)
    monkeypatch.setattr(worker, 'update_runs', lambda: None)
    monkeypatch.setattr(worker, 'process_refreshes', lambda: None)


def test_heartbeat_does_not_conflict_with_failure_update(monkeypatch):
    isolate_tick(monkeypatch)
    with db.Session.begin() as s:
        task = db.add(s, 'task', {'status':'running','lease_until':0})
    with db.Session() as s:
        # Hold the same ORM record that a completion/failure handler may hold.
        record = s.get(db.Record, task['id'])
        original = db.get(s, task['id'])
        worker.tick({task['id']:Future()}, None)
        db.put(s, task['id'], {**original,'status':'failed','lease_until':0})
        s.commit()
    worker.tick({task['id']:Future()}, None)
    with db.Session() as s:
        saved=db.get(s,task['id'])
        assert saved['status']=='failed'
        assert saved['lease_until']==0


def test_unhandled_item_error_does_not_stop_worker(monkeypatch):
    isolate_tick(monkeypatch)
    with db.Session.begin() as s:
        task=db.add(s,'task',{'status':'running','lease_until':123})
    future=Future()
    future.set_exception(RuntimeError('private details'))
    active={task['id']:future}
    worker.tick(active,None)
    assert not active
    with db.Session() as s:
        saved=db.get(s,task['id'])
        assert saved['status']=='failed'
        assert 'private details' not in saved['error']
