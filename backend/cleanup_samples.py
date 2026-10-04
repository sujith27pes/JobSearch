"""Remove bundled samples without deleting authored jobs or uploaded resumes."""
from collections import Counter
from pathlib import Path

from sqlalchemy import select, text

from . import store as db
from .services import update_runs

SAMPLE_JOBS={'job_demo_1','job_demo_2','job_demo_3'}


def remove_samples():
    paths=[]
    with db.Session.begin() as s:
        s.execute(text('BEGIN IMMEDIATE'))
        records=list(s.scalars(select(db.Record)))
        profiles={r.id for r in records if r.kind=='profile' and r.body.get('synthetic') is True}
        jobs={r.id for r in records if r.kind=='job' and r.id in SAMPLE_JOBS}
        if any(r.kind=='profile' and r.id not in profiles and r.body.get('job_id') in jobs for r in records):
            raise ValueError('An uploaded resume belongs to a sample job. Transfer it to an authored job before removing samples.')
        for r in records:
            if r.kind=='job' and r.id not in jobs and r.body.get('synthetic'):
                db.put(s,r.id,{**r.body,'synthetic':False})
        versions={r.id for r in records if r.kind=='profile_version' and r.body.get('profile_id') in profiles}
        rubrics={r.id for r in records if r.kind=='rubric' and r.body.get('job_id') in jobs}
        runs={r.id for r in records if r.kind=='run' and r.body.get('job_id') in jobs}
        owned=profiles|jobs|versions|rubrics|runs
        hashes={r.body.get('document_hash') for r in records if r.kind in ('profile','profile_version') and (r.id in profiles or r.body.get('profile_id') in profiles)}-{None}
        retained_hashes={r.body.get('document_hash') for r in records if r.kind in ('profile','profile_version') and r.id not in profiles and r.body.get('profile_id') not in profiles}-{None}
        # Extraction entries may also be owned through historical ingestion tasks.
        extraction={r.id:r.body for r in records if r.kind=='extraction_cache'}
        for r in records:
            if r.kind=='task' and r.body.get('extraction_cache_id') in extraction:
                h=extraction[r.body['extraction_cache_id']].get('document_hash')
                (hashes if r.body.get('profile_id') in profiles else retained_hashes).add(h)
        removed=Counter()
        for r in records:
            body=r.body
            if r.kind=='cache':
                owners=set(body.get('profile_ids',[]))
                if owners & profiles and owners-profiles:
                    replacement={**body,'profile_ids':sorted(owners-profiles)}
                    if replacement.get('profile_version') in versions:replacement.pop('profile_version')
                    db.put(s,r.id,replacement)
                    continue
                delete=bool(owners & profiles or body.get('profile_version') in versions)
            elif r.kind=='extraction_cache':
                delete=body.get('document_hash') in hashes-retained_hashes
            else:
                delete=r.id in owned or any(body.get(key) in owned for key in ('profile_id','job_id','profile_version','rubric_id','run_id','target_id'))
            if delete:
                if r.kind=='task' and body.get('upload_path'):
                    path=Path(body['upload_path']).resolve()
                    if path.is_relative_to((db.DATA/'uploads').resolve()):paths.append(path)
                removed[r.kind]+=1
                s.delete(r)
        s.flush()
        update_runs(s)
    for path in paths:path.unlink(missing_ok=True)
    return dict(removed)
