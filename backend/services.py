import time
from datetime import date, timedelta

from . import store as db
from .domain import eligibility, content_key, digest, score, consistency, union_months
from .intelligence import MODE, MODEL, PROMPT_VERSION, assess_profile

def needs_reassessment(a, criteria):
    method = a.get('prompt_version')!=PROMPT_VERSION or a.get('mode')!=MODE or (MODE=='ai' and a.get('engine')!=MODEL)
    timed = any(c.get('recency_months') or c.get('required_months') for c in criteria)
    return method or (timed and (a.get('evaluation_date') or '')[:7] != date.today().strftime('%Y-%m'))

def matching_eligible(p, job, exploratory=False, pools=None):
    return eligibility(p, None if exploratory and p['source_type']=='current_applicant' else job, pools=pools)[0]

def enriched_profile(p):
    from .insights import career_context, skill_freshness
    allowed,reason=eligibility(p)
    return {**p,'eligible':allowed,'eligibility_reason':reason,'consistency_flags':consistency(p['facts']),'total_months':union_months(p['facts'].get('roles',[])), 'career_context':career_context(p), 'skill_freshness':skill_freshness(p)}

def queue_run(s,job,rubric,idempotency=None,pools=None,profile_ids=None):
    runs=db.all_of(s,'run')
    if idempotency:
        existing=next((r for r in runs if r.get('idempotency_key')==idempotency and r['job_id']==job['id']),None)
        if existing:return existing
    # Reuse only work that covers this request. An applicant-only run must not
    # swallow a later search of all talent pools. Execution stays worker-bounded.
    eligible_profiles=[p for p in db.all_of(s,'profile') if (profile_ids is None or p['id'] in profile_ids) and eligibility(p,job,pools=pools)[0]]
    requested={(p['id'],p['version_id']) for p in eligible_profiles}
    tasks=db.all_of(s,'task')
    for existing in runs:
        if existing['status'] not in ('queued','running') or existing.get('kind') or existing['job_id']!=job['id'] or existing['rubric_id']!=rubric['id']:continue
        covered={(t['profile_id'],t['profile_version']) for t in tasks if t['run_id']==existing['id'] and t['status']!='excluded'}
        if requested and requested<=covered:return existing
    run=db.add(s,'run',{'job_id':job['id'],'rubric_id':rubric['id'],'status':'queued','total':0,'completed':0,'failed':0,'excluded':0,'reused':0,'idempotency_key':idempotency,'seconds':0})
    total=excluded=0
    for p in db.all_of(s,'profile'):
        if profile_ids is not None and p['id'] not in profile_ids:continue
        ok,reason=eligibility(p,job,pools=pools)
        if not ok:
            excluded+=1
            continue
        key=digest([p['version_id'],content_key(rubric['criteria']),MODE,MODEL,PROMPT_VERSION])
        db.add(s,'task',{'run_id':run['id'],'job_id':job['id'],'profile_id':p['id'],'profile_version':p['version_id'],'rubric_id':rubric['id'],'cache_key':key,'evaluation_date':date.today().isoformat(),'status':'queued','attempts':0,'lease_until':0,'heartbeat':0,'error':None})
        total+=1
    return db.put(s,run['id'],{**run,'total':total,'excluded':excluded,'status':'queued' if total else 'completed'})

def assessment_visible(s,a,pools=None):
    p=db.get(s,a['profile_id'],'profile'); j=db.get(s,a['job_id'],'job')
    return bool(p and j and p['version_id']==a['profile_version'] and eligibility(p,j,pools=pools)[0])

def collect_matches(s,job,pools=None):
    profiles=db.all_of(s,'profile')
    rows=[]
    for a in db.all_of(s,'assessment'):
        if a['job_id']!=job['id'] or a['rubric_id']!=job.get('rubric_id') or not assessment_visible(s,a,pools):continue
        p=next((p for p in profiles if p['id']==a['profile_id']),None)
        if p is None:continue
        review=db.get(s,'review_'+job['id']+'_'+p['id'],'review')
        rows.append({**a,'profile':enriched_profile(p),'review_status':review['status'] if review else 'not_reviewed','review_stage':review.get('stage','review') if review else 'review','review_revision':review['revision'] if review else 0})
    # Keep the newest interpretation per person; retain prior versions in history.
    latest={}
    for a in sorted(rows,key=lambda a:(a.get('created_at',''),a['id'])):
        a['needs_reassessment']=needs_reassessment(a,(db.get(s,a['rubric_id'],'rubric') or {}).get('criteria',[]))
        old=latest.get(a['profile_id'])
        if old is None or old['needs_reassessment'] or not a['needs_reassessment']:
            latest[a['profile_id']]=a
    rows=list(latest.values())
    rows.sort(key=lambda a:(-a['overall_score'],a['profile']['facts']['name']))
    rank=0;prev=None
    for n,a in enumerate(rows,1):
        if a['overall_score']!=prev:rank=n
        a['rank']=rank;prev=a['overall_score']
    return rows

def perform_task(task_id):
    start=time.monotonic()
    with db.Session() as s:
        task=db.get(s,task_id,'task')
        if not task:return
        if task.get('kind')=='ingest':
            from .ingestion import ingest
            ingest(task_id)
            return
        p=db.get(s,task['profile_id'],'profile');job=db.get(s,task['job_id'],'job');rubric=db.get(s,task['rubric_id'],'rubric')
        cached=db.get(s,'cache_'+task['cache_key'],'cache')
    if not p or not job or not rubric or p['version_id']!=task['profile_version'] or not matching_eligible(p,job,task.get('exploratory',False)):
        with db.Session.begin() as s:
            t=db.get(s,task_id)
            if t:db.put(s,task_id,{**t,'status':'excluded','error':'Profile is no longer eligible or has changed.'})
        return
    try:
        asof=date.fromisoformat(task.get('evaluation_date') or date.today().isoformat())
        if cached:
            from .insights import refresh_duration
            items=refresh_duration(cached['results'],p['facts'],cached.get('evaluation_date'),asof)
        else:
            with db.Session.begin() as s:
                t=db.get(s,task_id);db.put(s,task_id,{**t,'stage':'assessing'})
            items=assess_profile(p,rubric['criteria'],today=asof)
        result=score(rubric['criteria'],items,p['evidence'],p['facts'],today=asof)
        with db.Session.begin() as s:
            current=db.get(s,p['id'],'profile')
            if not current or current['version_id']!=p['version_id'] or not matching_eligible(current,job,task.get('exploratory',False)):
                t=db.get(s,task_id)
                if t:db.put(s,task_id,{**t,'status':'excluded','error':'Profile changed during assessment.'})
                return
            if not cached and not db.get(s,'cache_'+task['cache_key']):
                db.add(s,'cache',{'results':items,'evaluation_date':asof.isoformat(),'profile_ids':[p['id']],'profile_version':p['version_id']},'cache_'+task['cache_key'])
            kind='opportunity_assessment' if task.get('exploratory') else 'assessment'
            aid=kind+'_'+digest([p['version_id'],rubric['id'],MODE,MODEL,PROMPT_VERSION,asof.strftime('%Y-%m')])[:28]
            if not db.get(s,aid):
                db.add(s,kind,{**result,'profile_id':p['id'],'profile_version':p['version_id'],'job_id':job['id'],'rubric_id':rubric['id'],'rubric_version':rubric['version'],'engine':'Offline synthetic / rule-based preview' if MODE=='demo' else MODEL,'mode':MODE,'prompt_version':PROMPT_VERSION,'reused':bool(cached)},aid)
            t=db.get(s,task_id);db.put(s,task_id,{**t,'status':'completed','stage':'completed','assessment_id':aid,'seconds':round(time.monotonic()-start,3),'reused':bool(cached),'lease_until':0})
    except Exception as exc:
        # Only controlled errors are surfaced; provider responses and resume text are never logged.
        message=str(exc) if isinstance(exc,ValueError) else 'Processing failed. Check the document or model configuration and retry.'
        with db.Session.begin() as s:
            t=db.get(s,task_id)
            if t:db.put(s,task_id,{**t,'status':'failed','error':message[:500],'lease_until':0})

def update_runs(s=None):
    if s is None:
        with db.Session.begin() as owned:
            return update_runs(owned)
    tasks=db.all_of(s,'task')
    for r in db.all_of(s,'run'):
        own=[t for t in tasks if t['run_id']==r['id']]
        done=sum(t['status']=='completed' for t in own)
        failed=sum(t['status']=='failed' for t in own)
        excluded=sum(t['status']=='excluded' for t in own)
        status='running' if any(t['status'] in ('queued','running') for t in own) else ('completed_with_errors' if failed else 'completed')
        new={**r,'total':len(own),'completed':done,'failed':failed,'excluded_during_run':excluded,'status':status,'reused':sum(bool(t.get('reused')) for t in own),'seconds':round(sum(t.get('seconds',0) for t in own),2)}
        if any(new.get(k)!=r.get(k) for k in ('total','completed','failed','status','reused','seconds','excluded_during_run')):db.put(s,r['id'],new)

def process_refreshes():
    """Schedule automatic refreshes after explicit recruiter requests finish."""
    import os
    from .domain import SOURCES
    pools=os.getenv('JOBSCORE_ALLOWED_POOLS',','.join(SOURCES)).split(',')
    with db.Session.begin() as s:
        if any(r['status'] in ('queued','running') for r in db.all_of(s,'run')):return
        # Monthly arithmetic refresh reuses interpretations; no recurring model calls.
        for a in db.all_of(s,'assessment'):
            j=db.get(s,a['job_id'],'job');p=db.get(s,a['profile_id'],'profile')
            if not j or not p or j.get('rubric_id')!=a['rubric_id'] or p['version_id']!=a['profile_version']:continue
            rubric=db.get(s,a['rubric_id'],'rubric')
            marker='calendar_'+digest([p['version_id'],a['rubric_id'],date.today().strftime('%Y-%m')])[:24]
            key=digest([p['version_id'],content_key(rubric['criteria']),MODE,MODEL,PROMPT_VERSION])
            if needs_reassessment(a,rubric['criteria']) and db.get(s,'cache_'+key) and not db.get(s,marker) and eligibility(p,j,pools=pools)[0]:
                db.add(s,'refresh',{'profile_id':p['id'],'status':'queued','calendar_job_id':j['id']},marker)
        for refresh in db.all_of(s,'refresh'):
            if refresh['status']!='queued':continue
            p=db.get(s,refresh['profile_id'],'profile')
            done=refresh.get('job_ids_done',[])
            if not p:
                db.put(s,refresh['id'],{**refresh,'status':'completed'});continue
            jobs=[j for j in db.all_of(s,'job') if j.get('rubric_id') and j['id'] not in done and (not refresh.get('calendar_job_id') or j['id']==refresh['calendar_job_id']) and eligibility(p,j,pools=pools)[0]]
            if jobs:
                j=jobs[0]
                queue_run(s,j,db.get(s,j['rubric_id']),pools=pools,profile_ids=[p['id']])
                db.put(s,refresh['id'],{**refresh,'job_ids_done':done+[j['id']]})
                return
            db.put(s,refresh['id'],{**refresh,'status':'completed'})
