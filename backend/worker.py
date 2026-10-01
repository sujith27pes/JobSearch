"""Run separately: python -m backend.worker. Persisted queue with leases and recovery."""
import time
import os
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from . import store as db
from .services import perform_task,update_runs,process_refreshes

# Free API plans need less burst pressure; two remains the absolute maximum.
CONCURRENCY = 1 if os.getenv('JOBSCORE_MODE','demo')=='ai' else 2

def claim():
    with db.Session() as s:
        s.execute(text('BEGIN IMMEDIATE'))
        tasks=db.all_of(s,'task')
        t=next((t for t in tasks if t['status']=='queued' or (t['status']=='running' and t.get('lease_until',0)<time.time())),None)
        if t:
            db.put(s,t['id'],{**t,'status':'running','stage':'assessing','attempts':t['attempts']+1,'heartbeat':time.time(),'lease_until':time.time()+180})
        s.commit()
        return t

def tick(active,executor):
    for key,future in list(active.items()):
        if future.done():
            try:
                future.result()
            except Exception:
                # A failed item must never terminate the worker or expose source data.
                with db.Session() as s:
                    s.execute(text('BEGIN IMMEDIATE'))
                    t=db.get(s,key)
                    if t and t['status']=='running':
                        db.put(s,key,{**t,'status':'failed','error':'Processing interrupted by an internal error. Retry this item.','lease_until':0})
                    s.commit()
            del active[key]
        else:
            with db.Session.begin() as s:
                # Operational lease renewal must not change the business revision.
                # Atomic JSON updates preserve concurrent task fields and terminal states.
                s.execute(text("UPDATE records SET body=json_set(body, '$.heartbeat', :now, '$.lease_until', :lease) WHERE id=:id AND kind='task' AND json_extract(body, '$.status')='running'"),
                          {'now':time.time(),'lease':time.time()+180,'id':key})
    while len(active)<CONCURRENCY:
        t=claim()
        if not t:break
        active[t['id']]=executor.submit(perform_task,t['id'])
    update_runs()
    process_refreshes()

def main():
    print(f'JobScore worker ready. Maximum concurrency: {CONCURRENCY}. No document contents are logged.',flush=True)
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        active={}
        while True:
            tick(active,ex)
            time.sleep(1)

if __name__=='__main__':main()
