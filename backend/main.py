import csv
import html
import io
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import date,timedelta
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm.exc import StaleDataError

from . import store as db
from .schemas import JobCreate,RubricDraft,Approval,Scenario,Comparison,Review,ProfilePatch,Criterion
from .domain import SOURCES,eligibility,parsedate,add_months,digest,overlaps,scenarios
from .intelligence import MODE,MODEL,PROMPT_VERSION,extract_jd,parse_document,extract_facts
from .services import queue_run,collect_matches,enriched_profile,assessment_visible,needs_reassessment,update_runs

POOLS=[p.strip() for p in os.getenv('JOBSCORE_ALLOWED_POOLS',','.join(SOURCES)).split(',') if p.strip() in SOURCES]
ACTOR=os.getenv('JOBSCORE_ACTOR','local-recruiter')

@asynccontextmanager
async def lifespan(app):
    # Old practice-mode creation labelled authored jobs as seed examples.
    with db.Session.begin() as s:
        for j in db.all_of(s,'job'):
            if j.get('synthetic') and j['id'] not in ('job_demo_1','job_demo_2','job_demo_3'):
                db.put(s,j['id'],{**j,'synthetic':False})
    yield

app=FastAPI(title='JobScore API',version='2.0.0',lifespan=lifespan,description='Local synthetic-data hackathon build. Not an authenticated production deployment.')
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:5173','http://localhost:5173'],allow_methods=['GET','POST','PUT','PATCH','DELETE'],allow_headers=['Content-Type','Idempotency-Key'])

def session():
    with db.Session() as s:
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise

def need(s,id,kind):
    r=db.get(s,id,kind)
    if not r:raise HTTPException(404,'Record not found')
    return r

def access(p):
    if p['source_type'] not in POOLS:raise HTTPException(403,'Pool access restricted')

def version(record,revision):
    if record['revision']!=revision:raise HTTPException(409,'This record changed. Refresh before saving.')

def assessment(s,id):
    a=need(s,id,'assessment');p=need(s,a['profile_id'],'profile');access(p)
    if not assessment_visible(s,a,POOLS):raise HTTPException(410,'Assessment is no longer accessible: profile expired, changed, or left this pool.')
    return a,p

@app.exception_handler(ValueError)
async def validation_error(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422,content={'detail':str(exc)[:500]})

@app.exception_handler(StaleDataError)
async def stale_error(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409,content={'detail':'Record changed concurrently. Refresh before retrying.'})

@app.get('/api/health')
def health():return {'status':'ok','mode':MODE,'model':MODEL if MODE=='ai' else 'Offline rule-based preview','actor':ACTOR,'allowed_pools':POOLS,'production_ready':False}

@app.post('/api/model-connection/check')
def model_connection():
    from .connection import check_connection
    return check_connection()

@app.get('/api/stats')
def stats(s=Depends(session)):
    profiles=[p for p in db.all_of(s,'profile') if p['source_type'] in POOLS]
    runs=db.all_of(s,'run');usage=db.all_of(s,'usage')
    return {'profiles':len(profiles),'eligible':sum(eligibility(p,pools=POOLS)[0] for p in profiles),'jobs':len(db.all_of(s,'job')),'sources':{k:sum(p['source_type']==k and eligibility(p)[0] for p in profiles) for k in SOURCES},'model_calls':len(usage),'tokens':sum(u.get('total_tokens',0) for u in usage),'cost':sum(u['estimated_cost'] or 0 for u in usage) if usage and all(u['estimated_cost'] is not None for u in usage) else None,'reused':sum(r.get('reused',0) for r in runs),'active_runs':sum(r['status'] in ('queued','running') for r in runs)}

@app.get('/api/jobs')
def jobs(s=Depends(session)):
    return [{**j,'match_count':len(collect_matches(s,j,POOLS)),'last_run':next((r for r in reversed(db.all_of(s,'run')) if r['job_id']==j['id']),None)} for j in db.all_of(s,'job')]

@app.post('/api/jobs')
def create_job(data:JobCreate,s=Depends(session)):
    criteria=extract_jd(data.description)
    j=db.add(s,'job',{**data.model_dump(),'department':'New requisition','draft':criteria,'rubric_id':None,'synthetic':False})
    db.audit(s,'job_created',j['id'],'Job description submitted',ACTOR)
    return j

@app.get('/api/jobs/{id}')
def get_job(id:str,s=Depends(session)):
    j=need(s,id,'job')
    return {**j,'rubric':db.get(s,j['rubric_id']) if j.get('rubric_id') else None,'overlaps':overlaps(j['draft'])}

@app.put('/api/jobs/{id}/rubric-draft')
def draft(id:str,data:RubricDraft,s=Depends(session)):
    j=need(s,id,'job');version(j,data.revision)
    return db.put(s,id,{**j,'draft':[c.model_dump() for c in data.criteria]})

@app.post('/api/jobs/{id}/rubric-versions')
def approve(id:str,data:Approval,s=Depends(session)):
    j=need(s,id,'job');version(j,data.revision)
    criteria=[Criterion.model_validate(c).model_dump() for c in j['draft']]
    if not any(c['enabled'] and c['weight']>0 for c in criteria):raise ValueError('Enable at least one positively weighted criterion.')
    if overlaps(criteria) and not data.overlap_acknowledged:raise HTTPException(409,'Review overlapping criteria and acknowledge the intentional distinction before approving.')
    current=db.get(s,j['rubric_id']) if j.get('rubric_id') else None
    rubric=db.add(s,'rubric',{'job_id':id,'version':current['version']+1 if current else 1,'criteria':criteria,'approved_at':db.now(),'approved_by':ACTOR})
    j=db.put(s,id,{**j,'rubric_id':rubric['id']})
    selected=None if data.search_existing else [p['id'] for p in db.all_of(s,'profile') if p['source_type']=='current_applicant' and p.get('job_id')==id]
    r=queue_run(s,j,rubric,pools=POOLS,profile_ids=selected)
    db.audit(s,'rubric_approved',id,f"Approved rubric {rubric['version']}; authorised talent pools queued.",ACTOR)
    return {'job':j,'rubric':rubric,'run':r}

@app.post('/api/jobs/{id}/match-runs')
def match_run(id:str,idempotency_key:str|None=Header(default=None),s=Depends(session)):
    j=need(s,id,'job')
    if not j.get('rubric_id'):raise ValueError('Approve the rubric first.')
    return queue_run(s,j,need(s,j['rubric_id'],'rubric'),idempotency_key,POOLS)

@app.get('/api/jobs/{id}/matches')
def matches(id:str,s=Depends(session)):
    j=need(s,id,'job');rows=collect_matches(s,j,POOLS)
    ps=[p for p in db.all_of(s,'profile') if p['source_type'] in POOLS]
    eligible=sum(eligibility(p,j,pools=POOLS)[0] for p in ps)
    runs=[r for r in db.all_of(s,'run') if r['job_id']==id and r['rubric_id']==j.get('rubric_id')]
    eligible_ids={p['id'] for p in ps if eligibility(p,j,pools=POOLS)[0]}
    assessed_ids={a['profile_id'] for a in rows}
    failed_ids={t['profile_id'] for t in db.all_of(s,'task') if t.get('rubric_id')==j.get('rubric_id') and t['status']=='failed' and t['profile_id'] in eligible_ids and t['profile_id'] not in assessed_ids}
    pending_ids={t['profile_id'] for t in db.all_of(s,'task') if t['status'] in ('queued','running') and ((t.get('rubric_id')==j.get('rubric_id') and t['profile_id'] in eligible_ids) or (t.get('kind')=='ingest' and t.get('job_id')==id))}
    return {'rows':rows,'counts':{'eligible':eligible,'assessed':len(rows),'pending':len(pending_ids),'not_started':len(eligible_ids-assessed_ids-failed_ids-pending_ids),'excluded':len(ps)-eligible,'failed':len(failed_ids)},'run':runs[-1] if runs else None}

@app.get('/api/profiles')
def profiles(s=Depends(session)):
    return [enriched_profile(p) for p in db.all_of(s,'profile') if p['source_type'] in POOLS]

@app.get('/api/interviews')
def interviews(s=Depends(session)):
    """Interview tracking is distinct from eligibility for rediscovery."""
    jobs={j['id']:j for j in db.all_of(s,'job')}
    reviews=db.all_of(s,'review');events=db.all_of(s,'event');rows=[]
    for p in db.all_of(s,'profile'):
        if p['source_type'] not in POOLS or p.get('application_status')!='interview':continue
        if p['source_type']=='employee' and not p.get('internal_visibility'):continue
        # Apply shared permission/retention restrictions without rejected-only rules.
        if not eligibility({**p,'source_type':'current_applicant','processing_status':'ready'})[0]:continue
        moved=sorted([e for e in events if e['target_id']==p['id'] and e['action']=='moved_to_interview'],key=lambda e:e.get('at',''))
        event=moved[-1] if moved else {}
        job_id=p.get('interview_job_id')
        # Old moves did not store a job. Infer only an unambiguous reviewed job;
        # otherwise display the missing provenance rather than guess.
        if not job_id and event:
            candidates={r['job_id'] for r in reviews if r['profile_id']==p['id']}
            if len(candidates)==1:job_id=next(iter(candidates))
        rows.append({'profile_id':p['id'],'name':p['facts']['name'],'title':p['facts'].get('title',''),'source_type':p['source_type'],'synthetic':p.get('synthetic',False),'job_id':job_id,'job_title':jobs.get(job_id,{}).get('title','Job not recorded'),'stage':'interview','moved_at':p.get('interview_at') or event.get('at'),'actor':p.get('interview_actor') or event.get('actor'),'reason':p.get('interview_reason') or event.get('reason','Interview stage supplied by source; no recruiter move recorded.')})
    return sorted(rows,key=lambda r:r.get('moved_at') or '',reverse=True)

@app.patch('/api/profiles/{id}')
def patch_profile(id:str,data:ProfilePatch,s=Depends(session)):
    p=need(s,id,'profile');access(p);version(p,data.revision)
    if data.matching_allowed is True and not p['matching_allowed']:raise HTTPException(403,'A recruiter cannot override matching permission. Re-import an authorised source update.')
    changes=data.model_dump(exclude_none=True,exclude={'revision','reason','correction_text'})
    if data.application_status:
        if data.application_status=='rejected' and p.get('application_status')!='rejected':
            changes['rejected_at']=date.today().isoformat()
        if data.application_status in ('approved','interview','hired'):
            changes['active_interview']=True
        elif data.application_status in ('rejected','withdrawn'):
            changes['active_interview']=False
    if data.correction_text is not None:
        if not data.correction_text.strip():raise ValueError('Correction cannot remove all evidence.')
        evidence=[{'id':f'e{n+1}','location':f'Human correction · paragraph {n+1}','text':line} for n,line in enumerate(data.correction_text.splitlines()) if line.strip()]
        facts=extract_facts(evidence)
        vid=db.ident('pv');changes.update({'evidence':evidence,'facts':facts,'version_id':vid,'updated_at':date.today().isoformat(),'document_hash':digest(evidence),'processing_status':'ready'})
        db.add(s,'profile_version',{'profile_id':id,'facts':facts,'evidence':evidence,'document_hash':changes['document_hash'],'reason':data.reason},vid)
    p=db.put(s,id,{**p,**changes})
    db.audit(s,'profile_updated',id,data.reason,ACTOR)
    if data.correction_text is not None:
        db.add(s,'refresh',{'profile_id':id,'status':'queued'})
    return enriched_profile(p)

@app.delete('/api/profiles/{id}')
def delete_profile(id:str,s=Depends(session)):
    p=need(s,id,'profile');access(p)
    versions=[v['id'] for v in db.all_of(s,'profile_version') if v.get('profile_id')==id]
    hashes={p.get('document_hash')}
    hashes.update(v.get('document_hash') for v in db.all_of(s,'profile_version') if v.get('profile_id')==id)
    # Older versions can recover their file hash from persisted ingestion tasks.
    extraction_entries={r['id']:r for r in db.all_of(s,'extraction_cache')}
    hashes.update(extraction_entries.get(t.get('extraction_cache_id'),{}).get('document_hash') for t in db.all_of(s,'task') if t.get('profile_id')==id)
    for kind in ('assessment','profile_version','cache','task','review','refresh','opportunity_assessment'):
        for r in db.all_of(s,kind):
            if r.get('profile_id')==id or r.get('profile_version') in versions or id in r.get('profile_ids',[]):
                if kind=='task' and r.get('upload_path'):
                    path=Path(r['upload_path']).resolve()
                    if path.is_relative_to((db.DATA/'uploads').resolve()):path.unlink(missing_ok=True)
                db.remove(s,r['id'])
    remaining_ids={q['id'] for q in db.all_of(s,'profile') if q['id']!=id}
    shared_hashes={q.get('document_hash') for q in db.all_of(s,'profile') if q['id'] in remaining_ids}
    shared_hashes.update(v.get('document_hash') for v in db.all_of(s,'profile_version') if v.get('profile_id') in remaining_ids)
    shared_hashes.update(extraction_entries.get(t.get('extraction_cache_id'),{}).get('document_hash') for t in db.all_of(s,'task') if t.get('profile_id') in remaining_ids)
    for r in db.all_of(s,'extraction_cache'):
        if r.get('document_hash') in hashes and r.get('document_hash') not in shared_hashes:db.remove(s,r['id'])
    db.remove(s,id)
    update_runs(s)
    db.audit(s,'profile_deleted',id,'Profile and derived evidence removed. Event retains only opaque ID.',ACTOR)
    return {'deleted':True}

@app.get('/api/assessments/{id}')
def detail(id:str,s=Depends(session)):
    a,p=assessment(s,id)
    from .insights import skill_freshness
    a={**a,'skill_freshness':skill_freshness(p,a['results'])}
    r=db.get(s,'review_'+a['job_id']+'_'+p['id'])
    return {**a,'needs_reassessment':needs_reassessment(a,need(s,a['rubric_id'],'rubric')['criteria']),'profile':enriched_profile(p),'review_status':r['status'] if r else 'not_reviewed','review_revision':r['revision'] if r else 0,'history':[e for e in db.all_of(s,'event') if e['target_id'] in (p['id'],a['job_id'])]}

@app.post('/api/assessments/{id}/reassess')
def reassess(id:str,s=Depends(session)):
    a,p=assessment(s,id)
    j=need(s,a['job_id'],'job')
    return queue_run(s,j,need(s,j['rubric_id'],'rubric'),pools=POOLS,profile_ids=[p['id']])

@app.post('/api/assessments/{id}/scenarios')
def simulate(id:str,data:Scenario,s=Depends(session)):
    a,_=assessment(s,id);return scenarios(a,data.target)

@app.post('/api/jobs/{id}/comparisons')
def compare(id:str,data:Comparison,s=Depends(session)):
    j=need(s,id,'job')
    if len(set(data.assessment_ids))!=len(data.assessment_ids):raise ValueError('Select distinct candidates.')
    candidates=[]
    for aid in data.assessment_ids:
        a,p=assessment(s,aid)
        if a['job_id']!=id or a['rubric_id']!=j['rubric_id']:raise ValueError('Compare candidates against the same current rubric.')
        candidates.append({**a,'name':p['facts']['name'],'source_type':p['source_type']})
    from itertools import combinations
    pairs=[]
    for a,b in combinations(candidates,2):
        right={r['criterion_id']:r for r in b['results']}
        differences=sorted([{'criterion_id':r['criterion_id'],'criterion':r['requirement'],'delta':round(r['contribution']-right[r['criterion_id']]['contribution'],2)} for r in a['results']],key=lambda x:(-abs(x['delta']),x['criterion_id']))
        pairs.append({'left_id':a['id'],'right_id':b['id'],'left_name':a['name'],'right_name':b['name'],'differences':differences[:3]})
    return {'candidates':candidates,'differences':pairs[0]['differences'],'pairwise_differences':pairs}

@app.patch('/api/jobs/{id}/profiles/{profile_id}/review')
def review(id:str,profile_id:str,data:Review,s=Depends(session)):
    j=need(s,id,'job');p=need(s,profile_id,'profile');access(p)
    rid='review_'+id+'_'+profile_id;r=db.get(s,rid)
    if (r['revision'] if r else 0)!=data.revision:raise HTTPException(409,'Review changed. Refresh first.')
    rejecting=data.status=='rejected'
    already_rejected=p['source_type']=='past_applicant' and p.get('application_status')=='rejected' and p.get('rejected_job_id')==id
    if rejecting and not (already_rejected or (p['source_type']=='current_applicant' and p.get('job_id')==id)):
        raise ValueError('Reject this job\'s current applicants. Use Not shortlisted for rediscovered or internal candidates.')
    if rejecting and 'past_applicant' not in POOLS:raise HTTPException(403,'This workspace cannot move applicants into the past-applicant pool.')
    checked={**p,'source_type':'current_applicant'} if rejecting and already_rejected else p
    if not eligibility(checked,j,pools=POOLS)[0]:raise HTTPException(410,'Profile is no longer eligible for this job.')
    body={'job_id':id,'profile_id':profile_id,'status':'shortlisted' if data.move_to_interview else data.status,'stage':'rejected' if rejecting else ('interview' if data.move_to_interview else (r.get('stage','review') if r else 'review')),'reason':data.reason,'actor':ACTOR}
    result=db.put(s,rid,{**body,'revision':data.revision}) if r else db.add(s,'review',body,rid)
    if rejecting and not already_rejected:
        other_interview=bool(p.get('active_interview') and p.get('interview_job_id') and p['interview_job_id']!=id)
        rejected_at=p.get('rejected_at') if p.get('application_status')=='rejected' and parsedate(p.get('rejected_at')) else date.today().isoformat()
        db.put(s,profile_id,{**p,'source_type':'past_applicant','application_status':'rejected','rejected_at':rejected_at,'rejected_job_id':id,'rejection_reason':data.reason,'rejection_actor':ACTOR,'rejection_recorded_at':db.now(),'active_interview':other_interview,'previous_job_title':j['title'],'previous_stage':p.get('application_status','applied'),'previous_outcome':data.reason})
    elif data.move_to_interview:
        db.put(s,profile_id,{**p,'application_status':'interview','active_interview':True,'interview_job_id':id,'interview_at':db.now(),'interview_actor':ACTOR,'interview_reason':data.reason})
    db.audit(s,'application_rejected' if rejecting else ('moved_to_interview' if data.move_to_interview else 'review_updated'),profile_id,data.reason,ACTOR)
    return result

@app.get('/api/processing')
def processing(s=Depends(session)):
    ps={p['id']:p for p in db.all_of(s,'profile') if p['source_type'] in POOLS}
    titles={j['id']:j['title'] for j in db.all_of(s,'job')}
    tasks=[{**t,'name':ps[t['profile_id']]['facts']['name'],'job_title':titles.get(t.get('job_id'),'Talent import')} for t in db.all_of(s,'task') if t['profile_id'] in ps]
    latest={}
    for t in sorted(tasks,key=lambda t:(t.get('created_at',''),t['id'])):
        key=(t['profile_id'],t.get('job_id'),t.get('kind','assessment'),bool(t.get('exploratory')))
        latest[key]=t['id']
    jobs={j['id']:j for j in db.all_of(s,'job')}
    for t in tasks:
        key=(t['profile_id'],t.get('job_id'),t.get('kind','assessment'),bool(t.get('exploratory')))
        current_version=t.get('profile_version')==ps[t['profile_id']]['version_id']
        current_rubric=t.get('kind')=='ingest' or t.get('rubric_id')==jobs.get(t.get('job_id'),{}).get('rubric_id')
        t['is_current']=latest[key]==t['id'] and current_version and current_rubric
    runs=[{**r,'job_title':titles.get(r.get('job_id'),'Talent import')} for r in db.all_of(s,'run')]
    return {'runs':list(reversed(runs)),'tasks':list(reversed(tasks)),'usage':db.all_of(s,'usage')}

@app.get('/api/processing/{run_id}')
def processing_run(run_id:str,s=Depends(session)):
    r=need(s,run_id,'run')
    tasks=[t for t in processing(s)['tasks'] if t['run_id']==run_id]
    return {**r,'tasks':tasks}

@app.post('/api/processing/{task_id}/retry')
def retry(task_id:str,s=Depends(session)):
    t=need(s,task_id,'task');p=need(s,t['profile_id'],'profile');access(p)
    if t['status']!='failed':raise ValueError('Only failed tasks can be retried.')
    if not next((x.get('is_current') for x in processing(s)['tasks'] if x['id']==task_id),False):raise HTTPException(409,'This is an older attempt. Open the latest resume activity or run a new search for the current profile and job requirements.')
    if not eligibility({**p,'processing_status':'ready'} if t.get('kind')=='ingest' else p,need(s,t['job_id'],'job') if t.get('job_id') else None,pools=POOLS)[0]:raise ValueError('Profile is no longer eligible.')
    if t.get('kind')=='ingest':db.put(s,p['id'],{**p,'processing_status':'queued'})
    result=db.put(s,task_id,{**t,'status':'queued','stage':'queued','error':None,'lease_until':0})
    update_runs(s)
    return result

def cell(value):
    v=str(value)
    return "'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r')) else v

@app.get('/api/jobs/{id}/exports')
def export(id:str,format:str='csv',s=Depends(session)):
    j=need(s,id,'job');rows=collect_matches(s,j,POOLS)
    if format=='json':
        body=json.dumps({'job':j,'assessments':rows},ensure_ascii=False,indent=2);media='application/json'
    elif format=='html':
        esc=html.escape
        body='<html lang="en"><meta charset="utf-8"><title>JobScore report</title><style>body{font:15px system-ui;max-width:1000px;margin:40px auto;color:#17233b}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:10px;text-align:left}article{margin:35px 0}small{color:#667085}</style><h1>'+esc(j['title'])+'</h1><p>Documented match, not a prediction of hiring success. '+esc(MODE)+' mode.</p>'
        for a in rows:
            body+='<article><h2>'+esc(a['profile']['facts']['name'])+' · '+str(a['overall_score'])+'/100</h2><p>'+esc(a['summary'])+'</p><small>Rubric '+str(a['rubric_version'])+' · '+esc(a['profile']['source_type'])+'</small><table><tr><th>Criterion</th><th>Status</th><th>Evidence</th></tr>'
            for r in a['results']:
                ev=' | '.join(e['location']+': '+e['text'] for e in a['profile']['evidence'] if e['id'] in r['evidence_ids'])
                body+='<tr><td>'+esc(r['requirement'])+'</td><td>'+esc(r['status'])+'</td><td>'+esc(ev)+'</td></tr>'
            body+='</table></article>'
        body+='</html>';media='text/html'
    elif format=='csv':
        out=io.StringIO();w=csv.writer(out);w.writerow(['Candidate','Source','Score','Coverage','Review','Rubric','Summary'])
        for a in rows:w.writerow([cell(a['profile']['facts']['name']),a['profile']['source_type'],a['overall_score'],a['coverage'],a['review_status'],a['rubric_version'],cell(a['summary'])])
        body=out.getvalue();media='text/csv'
    else:raise ValueError('Choose csv, html, or json.')
    return Response(body,media_type=media,headers={'Content-Disposition':f'attachment; filename="jobscore-report.{format}"'})

@app.post('/api/imports')
def imports(files:list[UploadFile]=File(...),manifest:UploadFile|None=File(None),job_id:str|None=Form(None),source_type:str=Form('current_applicant'),profile_id:str|None=Form(None),profile_revision:int|None=Form(None),idempotency_key:str|None=Header(None),s=Depends(session)):
    if source_type not in POOLS:raise HTTPException(403,'Pool access restricted')
    if idempotency_key:
        old=next((r for r in db.all_of(s,'import') if r.get('key')==idempotency_key),None)
        if old:return old
    replacement=None
    if profile_id:
        if manifest or len(files)!=1:raise ValueError('Replacing a resume requires exactly one file and no manifest.')
        replacement=need(s,profile_id,'profile');access(replacement)
        if profile_revision is None:raise ValueError('Refresh the candidate list before replacing a resume.')
        version(replacement,profile_revision)
        if replacement['source_type']!='current_applicant' or replacement.get('job_id')!=job_id:raise ValueError('Choose an applicant belonging to this job. Source-managed profiles require an authorised manifest update.')
        if replacement.get('synthetic'):raise ValueError('Sample profiles cannot be replaced with real resumes.')
    metadata={}
    if manifest:
        content=manifest.file.read(1024*1024+1)
        if len(content)>1024*1024:raise ValueError('Manifest exceeds 1 MB.')
        try:
            decoded=content.decode('utf-8-sig')
        except UnicodeError:
            raise ValueError('Manifest must be a UTF-8 CSV file.') from None
        reader=csv.DictReader(io.StringIO(decoded))
        required={'source_type','source_record_id','filename','updated_at','matching_allowed','retention_expires_at'}
        if not required <= set(reader.fieldnames or []):raise ValueError('Manifest is missing required columns.')
        for row in reader:
            if None in row:raise ValueError('Manifest rows contain more values than the header.')
            row={k:(v or '').strip() for k,v in row.items()}
            if any(not row.get(k) for k in required):raise ValueError('Every manifest row must supply source, identity, filename, dates and matching permission.')
            if row['filename'] in metadata:raise ValueError('Manifest filenames must be unique.')
            metadata[row['filename']]=row
    if len(files)>30:raise ValueError('Maximum 30 files per batch.')
    if source_type!='current_applicant' and not manifest:raise ValueError('Past applicants and employees require a manifest with permission and lifecycle metadata.')
    successes=[];errors=[]
    ingest_run=db.add(s,'run',{'job_id':job_id,'rubric_id':None,'kind':'ingest','status':'queued','total':0,'completed':0,'failed':0,'excluded':0,'reused':0,'seconds':0})
    for f in files:
        filename=Path(f.filename or '').name
        upload_path=None
        accepted=False
        try:
            with s.begin_nested():
                m=metadata.get(filename,{})
                if manifest and not m:raise ValueError('No manifest entry for this file.')
                src=m.get('source_type',source_type)
                if src not in POOLS:raise ValueError('Pool access restricted.')
                if src=='current_applicant':
                    if not job_id:raise ValueError('Choose the job receiving this application.')
                    need(s,job_id,'job')
                status=m.get('application_status') or 'applied'
                if status not in ('applied','rejected','approved','interview','hired','withdrawn'):raise ValueError('Invalid application_status in manifest.')
                rejected=m.get('rejected_at')
                if rejected and not parsedate(rejected):raise ValueError('rejected_at must be an ISO date.')
                if src=='past_applicant' and (m.get('application_status')!='rejected' or not parsedate(rejected)):
                    raise ValueError('Rediscovery imports require application_status=rejected and a valid rejected_at date.')
                content=f.file.read(10*1024*1024+1)
                if len(content)>10*1024*1024:raise ValueError('File exceeds 10 MB.')
                import hashlib
                h=hashlib.sha256(content).hexdigest()
                sid=m.get('source_record_id') or (replacement['source_record_id'] if replacement else db.ident('upload'))
                existing=next((p for p in db.all_of(s,'profile') if p['source_type']==src and p['source_record_id']==sid),None)
                if not manifest and not replacement:
                    existing=next((p for p in db.all_of(s,'profile') if p['source_type']==src and p.get('job_id')==job_id and p.get('document_hash')==h and not p.get('synthetic')),None)
                    if existing:
                        successes.append({'id':existing['id'],'filename':filename,'cached':True,'status':existing.get('processing_status','ready'),'unchanged':True})
                        continue
                    ambiguous=[p for p in db.all_of(s,'profile') if p['source_type']==src and p.get('job_id')==job_id and p.get('filename','').casefold()==filename.casefold() and not p.get('synthetic')]
                    if ambiguous:raise ValueError('A different resume with this filename already exists. Choose Replace an existing candidate, or rename the file if this is a new applicant.')
                if existing and existing.get('processing_status') in ('queued','extracting'):raise ValueError('This candidate already has a resume being processed. Wait for it to finish before replacing it.')
                if not existing and sum(not p.get('synthetic',False) for p in db.all_of(s,'profile'))>=30:raise ValueError('This workspace has reached its limit of 30 uploaded profiles. Remove an unused uploaded profile before adding another. Sample profiles do not use this allowance.')
                cacheid='extraction_'+digest([h,MODE,MODEL,PROMPT_VERSION])
                cached=db.get(s,cacheid)
                if not filename.lower().endswith(('.pdf','.docx')):raise ValueError('Only PDF and DOCX documents are supported.')
                ev=[]
                facts={'name':filename.rsplit('.',1)[0].replace('_',' '),'title':'Awaiting extraction','roles':[],'skills':[],'stated_months':None}
                def flag(key,default=False):
                    value=m.get(key)
                    if value in (None,''):return default
                    if value.lower() not in ('true','false','1','0'):raise ValueError(f'{key} must be true or false.')
                    return value.lower() in ('true','1')
                expires=m.get('retention_expires_at') or (date.today()+timedelta(days=90)).isoformat()
                updated=m.get('updated_at') or date.today().isoformat()
                if not parsedate(expires) or not parsedate(updated):raise ValueError('Update and retention dates must be ISO dates.')
                pid=existing['id'] if existing else db.ident('profile');vid=db.ident('pv')
                body={'source_type':src,'source_record_id':sid,'filename':filename,'updated_at':updated,'retention_expires_at':existing['retention_expires_at'] if replacement else expires,'matching_allowed':existing['matching_allowed'] if replacement else flag('matching_allowed',True),'internal_visibility':flag('internal_visibility'),'suppressed':existing.get('suppressed',False) if existing else False,'application_status':existing.get('application_status','applied') if replacement else status,'rejected_at':existing.get('rejected_at') if replacement else rejected,'active_interview':existing.get('active_interview',False) if existing else False,'previous_job_title':m.get('previous_job_title'),'previous_stage':m.get('previous_stage'),'previous_outcome':m.get('previous_outcome'),'silver_medalist':flag('silver_medalist'),'job_id':job_id if src=='current_applicant' else None,'facts':facts,'evidence':ev,'version_id':vid,'document_hash':h,'synthetic':False,'processing_status':'queued'}
                if existing:
                    for field in ('interview_job_id','interview_at','interview_actor','interview_reason','rejected_job_id','rejection_reason','rejection_actor','rejection_recorded_at'):
                        if field in existing:body[field]=existing[field]
                    if existing.get('rejected_job_id'):
                        for field in ('rejected_at','job_id','previous_job_title','previous_stage','previous_outcome'):
                            body[field]=existing.get(field)
                    if existing.get('active_interview') and existing.get('application_status')=='interview':
                        body['application_status']='interview'
                        body['facts']=existing['facts']
                folder=db.DATA/'uploads';folder.mkdir(exist_ok=True)
                upload_path=folder/(db.ident('document')+Path(filename).suffix.lower())
                upload_path.write_bytes(content)
                p=db.put(s,pid,body) if existing else db.add(s,'profile',body,pid)
                db.add(s,'task',{'kind':'ingest','run_id':ingest_run['id'],'job_id':job_id,'profile_id':pid,'profile_version':vid,'extraction_cache_id':cacheid,'upload_path':str(upload_path),'status':'queued','stage':'queued','attempts':0,'lease_until':0,'error':None})
                db.audit(s,'profile_imported',pid,'Source profile queued for extraction.',ACTOR)
            accepted=True
            successes.append({'id':pid,'filename':filename,'cached':bool(cached),'status':'queued'})
        except (ValueError,UnicodeError) as exc:errors.append({'filename':filename,'error':str(exc)[:300]})
        except Exception:errors.append({'filename':filename,'error':'Document processing failed; verify the file and retry.'})
        finally:
            if upload_path and not accepted:
                upload_path.unlink(missing_ok=True)
    db.put(s,ingest_run['id'],{**ingest_run,'total':sum(not x.get('unchanged') for x in successes),'status':'queued' if any(not x.get('unchanged') for x in successes) else 'completed'})
    return db.add(s,'import',{'key':idempotency_key,'run_id':ingest_run['id'],'successes':successes,'errors':errors})

from .insights_api import router as insights_router
app.include_router(insights_router(session,need,access,lambda:POOLS))

dist=db.ROOT/'frontend'/'dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path:str):
        from fastapi.responses import FileResponse
        if path.startswith('api/'):raise HTTPException(404,'Unknown API endpoint')
        return FileResponse(dist/'index.html')
