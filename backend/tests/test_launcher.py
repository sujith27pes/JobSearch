"""The launcher must fail clearly and clean up its own child processes."""
import sys
from urllib.error import URLError

import pytest
import run as launcher


class Child:
    def __init__(self,results=()):
        self.results=iter(results);self.stopped=False;self.waited=False
    def poll(self):return next(self.results,None)
    def terminate(self):self.stopped=True
    def wait(self,timeout=None):self.waited=True


class Probe:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def bind(self,address):pass


@pytest.fixture
def setup_launcher(monkeypatch):
    monkeypatch.setattr(launcher,'load_env',lambda:None)
    monkeypatch.setattr(sys,'argv',['run.py'])
    monkeypatch.setattr(launcher.socket,'socket',lambda:Probe())
    monkeypatch.setattr(launcher.time,'sleep',lambda _:None)


def test_launcher_waits_for_health_before_opening_browser(monkeypatch,setup_launcher):
    api=Child([None,None,1]);worker=Child();children=iter([api,worker])
    monkeypatch.setattr(launcher.subprocess,'Popen',lambda *args,**kwargs:next(children))
    checks=[];opened=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def health(*args,**kwargs):
        checks.append(True)
        assert not opened
        if len(checks)==1:raise URLError('Starting')
        return Response()
    monkeypatch.setattr(launcher,'urlopen',health)
    monkeypatch.setattr(launcher.webbrowser,'open',lambda _:opened.append(len(checks)))
    with pytest.raises(SystemExit,match='stopped unexpectedly'):launcher.main()
    assert opened==[2] and worker.stopped and api.waited and worker.waited


def test_child_start_failure_cleans_up_started_server(monkeypatch,setup_launcher):
    api=Child();calls=[]
    def start(*args,**kwargs):
        calls.append(True)
        if len(calls)==2:raise OSError('Worker could not start')
        return api
    monkeypatch.setattr(launcher.subprocess,'Popen',start)
    with pytest.raises(OSError):launcher.main()
    assert api.stopped and api.waited


def test_occupied_port_does_not_launch_children_or_browser(monkeypatch,setup_launcher):
    class Busy(Probe):
        def bind(self,address):raise OSError('Occupied')
    monkeypatch.setattr(launcher.socket,'socket',lambda:Busy())
    def forbidden(*args,**kwargs):pytest.fail('Must not launch while port is occupied')
    monkeypatch.setattr(launcher.subprocess,'Popen',forbidden)
    monkeypatch.setattr(launcher.webbrowser,'open',forbidden)
    with pytest.raises(SystemExit,match='Port 8000 is already in use'):launcher.main()
