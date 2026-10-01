"""Portable local launcher: python run.py. Binds only to localhost."""
import os
import subprocess
import sys
import time
import webbrowser
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
    if not (ROOT/'frontend'/'dist'/'index.html').exists():
        raise SystemExit('Build the frontend first: cd frontend; npm install; npm run build')
    try:
        import fastapi,sqlalchemy,uvicorn
    except ImportError:
        raise SystemExit('Install dependencies first: python -m pip install -r backend/requirements.txt')
    print('Starting JobScore at http://127.0.0.1:8000. Press Ctrl+C to stop both processes.')
    processes=[subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT),subprocess.Popen([sys.executable,'-m','backend.worker'],cwd=ROOT)]
    try:
        time.sleep(2)
        if '--no-browser' not in sys.argv:webbrowser.open('http://127.0.0.1:8000')
        while all(p.poll() is None for p in processes):time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=8)
            except subprocess.TimeoutExpired:p.kill()

if __name__=='__main__':main()
