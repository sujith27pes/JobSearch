"""Read-only monitoring and explicit, budgeted exploration of other job fits."""
from datetime import date
from fastapi import APIRouter,Depends,HTTPException
from . import store as db
from .schemas import OpportunityRequest
from .domain import eligibility, content_key, digest, SOURCES
from .intelligence import MODE,MODEL,PROMPT_VERSION
from .services import collect_matches,matching_eligible,needs_reassessment


def router(session,need,access,pool_provider):
    api=APIRouter()

    @api.get('/api/monitoring')
    def monitoring(include_samples:bool=False,s=Depends(session)):
        pools=pool_provider()
        jobs=db.all_of(s,'job')
        rows=[a for j in jobs for a in collect_matches(s,j,pools) if include_samples or not a['profile'].get('synthetic')]
        bins=[{'label':'0–19','min':0,'max':19},{'label':'20–39','min':20,'max':39},{'label':'40–59','min':40,'max':59},{'label':'60–79','min':60,'max':79},{'label':'80–100','min':80,'max':100}]
        groups=[]
        for source in SOURCES:
            if source not in pools:continue
            selected=[a for a in rows if a['profile']['source_type']==source]
            groups.append({'source':source,'count':len(selected),'bins':[{**b,'count':sum(b['min']<=a['overall_score']<=b['max'] for a in selected)} for b in bins], 'mean_coverage':round(sum(a['coverage'] for a in selected)/len(selected)) if len(selected)>=5 else None, 'essential_unresolved':sum(a['essentials']['not_evidenced']>0 for a in selected), 'stale':sum(a['needs_reassessment'] for a in selected)})
        # One latest retained profile/job record per evaluation month. Historical rubric is labelled.
        retained={a['profile_id']:a['profile'] for a in rows}
        latest={}
        for a in db.all_of(s,'assessment'):
            p=retained.get(a['profile_id'])
            if not p or a['profile_version']!=p['version_id']:continue
            if not include_samples and p.get('synthetic'):continue
            month=(a.get('evaluation_date') or a.get('created_at',''))[:7]
            key=(month,a['job_id'],a['profile_id'])
            if key not in latest or latest[key].get('created_at','')<a.get('created_at',''):latest[key]=a
        months=sorted({key[0] for key in latest})
        trend=[{'month':m,'count':sum(k[0]==m for k in latest),'mean_score':round(sum(a['overall_score'] for k,a in latest.items() if k[0]==m)/sum(k[0]==m for k in latest),1) if sum(k[0]==m for k in latest)>=5 else None,'rubric_count':len({a['rubric_id'] for k,a in latest.items() if k[0]==m})} for m in months]
        return {'assessment_count':len(rows),'candidate_count':len(retained),'groups':groups,'trend':trend,'include_samples':include_samples,'note':'Pool distributions monitor assessment behaviour; they do not measure protected-group adverse impact. Different roles, rubrics and small samples are not directly comparable. Expired, suppressed and inaccessible profiles are excluded.'}

    @api.get('/api/profiles/{id}/opportunities')
    def opportunities(id:str,s=Depends(session)):
        pools=pool_provider()
        p=need(s,id,'profile');access(p)
        if not eligibility(p,pools=pools)[0]:raise HTTPException(410,'This profile is no longer eligible for matching.')
        jobs={j['id']:j for j in db.all_of(s,'job')}
        latest={}
        for a in db.all_of(s,'opportunity_assessment'):
            j=jobs.get(a['job_id'])
            if a['profile_id']!=id or a['profile_version']!=p['version_id'] or not j or a['rubric_id']!=j.get('rubric_id') or not matching_eligible(p,j,True,pools):continue
            a={**a,'job_title':j['title'],'needs_refresh':needs_reassessment(a,db.get(s,a['rubric_id'])['criteria'])}
            if j['id'] not in latest or latest[j['id']].get('created_at','')<a.get('created_at',''):latest[j['id']]=a
        own=jobs.get(p.get('job_id'))
        baseline=collect_matches(s,own,pools) if own else []
        original=next((a for a in baseline if a['profile_id']==id),None)
        tasks=[t for t in db.all_of(s,'task') if t.get('exploratory') and t['profile_id']==id and t['profile_version']==p['version_id']]
        latest_tasks={}
        for t in tasks:latest_tasks[t['job_id']]=t
        available=[{'id':j['id'],'title':j['title']} for j in jobs.values() if j.get('rubric_id') and j['id']!=p.get('job_id') and matching_eligible(p,j,True,pools)]
        return {'available_jobs':available,'rows':sorted(latest.values(),key=lambda a:-a['overall_score']),'original_score':original['overall_score'] if original else None,'original_job':own['title'] if own else None,'pending':sum(t['status'] in ('queued','running') for t in latest_tasks.values()),'failures':[{'job_title':jobs.get(t['job_id'],{}).get('title','Job'),'error':t.get('error')} for t in latest_tasks.values() if t['status']=='failed'], 'note':'Scores describe fit against different approved job requirements; a higher score is a lead to review, not a hiring recommendation. Applications and review stages are unchanged.'}

    @api.post('/api/profiles/{id}/opportunities')
    def find_opportunities(id:str,data:OpportunityRequest|None=None,s=Depends(session)):
        pools=pool_provider()
        p=need(s,id,'profile');access(p)
        if not eligibility(p,pools=pools)[0]:raise HTTPException(410,'This profile is no longer eligible for matching.')
        if any(t.get('exploratory') and t['profile_id']==id and t['profile_version']==p['version_id'] and t['status'] in ('queued','running') for t in db.all_of(s,'task')):raise ValueError('Other roles are already being assessed for this candidate. Wait for Activity to finish.')
        jobs=[j for j in db.all_of(s,'job') if j.get('rubric_id') and j['id']!=p.get('job_id') and matching_eligible(p,j,True,pools)]
        if data is not None and data.job_ids is not None:
            if len(set(data.job_ids))!=len(data.job_ids):raise ValueError('Choose distinct jobs.')
            if not set(data.job_ids)<={j['id'] for j in jobs}:raise ValueError('One selected job is no longer approved or eligible.')
            jobs=[j for j in jobs if j['id'] in data.job_ids]
        elif len(jobs)>3:raise ValueError('Choose up to three other jobs to stay within the request allowance.')
        existing=opportunities(id,s)['rows']
        jobs=[j for j in jobs if not any(a['job_id']==j['id'] and not a['needs_refresh'] for a in existing)]
        if len(jobs)>3:raise ValueError('This demonstration supports exploring up to three other approved jobs. Reduce the open job set before continuing.')
        run=db.add(s,'run',{'job_id':p.get('job_id'),'rubric_id':None,'kind':'opportunities','status':'queued' if jobs else 'completed','total':len(jobs),'completed':0,'failed':0,'excluded':0,'reused':0,'seconds':0})
        for j in jobs:
            rubric=db.get(s,j['rubric_id'])
            key=digest([p['version_id'],content_key(rubric['criteria']),MODE,MODEL,PROMPT_VERSION])
            db.add(s,'task',{'exploratory':True,'run_id':run['id'],'job_id':j['id'],'profile_id':p['id'],'profile_version':p['version_id'],'rubric_id':rubric['id'],'cache_key':key,'evaluation_date':date.today().isoformat(),'status':'queued','stage':'queued','attempts':0,'lease_until':0,'heartbeat':0,'error':None})
        db.audit(s,'other_roles_requested',id,'Recruiter explicitly requested matching against other approved jobs; no application was transferred.')
        return run
    return api
