"""Portable local launcher: python run.py. Binds only to localhost."""
import os
import subprocess
import sys
import time
import webbrowser
import socket
from urllib.request import urlopen
from urllib.error import URLError
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def load_env():
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key,value=line.split('=',1)
                os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))

def main():
    load_env()
    if '--check-model' in sys.argv or '--test-model' in sys.argv:
        from backend.connection import print_check
        raise SystemExit(print_check(generate='--test-model' in sys.argv))
    if not (ROOT/'frontend'/'dist'/'index.html').exists():
        raise SystemExit('Build the frontend first: cd frontend; npm install; npm run build')
    try:
        import fastapi,sqlalchemy,uvicorn
    except ImportError:
        raise SystemExit('Install dependencies first: python -m pip install -r backend/requirements.txt')
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',8000))
        except OSError:raise SystemExit('Port 8000 is already in use. Stop the existing launcher before starting JobScore again.') from None
    print('Starting JobScore at http://127.0.0.1:8000. Press Ctrl+C to stop both processes.')
    processes=[]
    try:
        processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT))
        processes.append(subprocess.Popen([sys.executable,'-m','backend.worker'],cwd=ROOT))
        deadline=time.monotonic()+30
        while True:
            if any(p.poll() is not None for p in processes):
                raise SystemExit('JobScore failed to start. See the server or worker error above.')
            try:
                with urlopen('http://127.0.0.1:8000/api/health',timeout=1) as response:
                    if response.status==200:break
            except (URLError,TimeoutError,OSError):pass
            if time.monotonic()>=deadline:raise SystemExit('JobScore did not become ready within 30 seconds. See the server output above.')
            time.sleep(.25)
        if '--no-browser' not in sys.argv:webbrowser.open('http://127.0.0.1:8000')
        while all(p.poll() is None for p in processes):time.sleep(1)
        raise SystemExit('The JobScore server or worker stopped unexpectedly. Restart the launcher; saved work is retained.')
    except KeyboardInterrupt:pass
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

if __name__=='__main__':main()
