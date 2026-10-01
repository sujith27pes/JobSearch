"""Restart-safe document ingestion. Raw uploads are removed after successful extraction."""
from pathlib import Path
from . import store as db
from .domain import digest,eligibility
from .intelligence import MODE,MODEL,PROMPT_VERSION,parse_document,extract_facts

def ingest(task_id):
    with db.Session() as s:
        t=db.get(s,task_id)
        if not t:return
        p=db.get(s,t['profile_id'],'profile')
        cached=db.get(s,t['extraction_cache_id'])
    if not p:return
    path=Path(t['upload_path'])
    try:
        ok,reason=eligibility({**p,'processing_status':'ready'})
        if not ok:raise ValueError('Extraction withheld: '+reason)
        if p['version_id']!=t['profile_version']:raise ValueError('A newer profile version superseded this upload.')
        if cached:
            evidence,facts=cached['evidence'],cached['facts']
        else:
            with db.Session.begin() as s:
                current=db.get(s,task_id);db.put(s,task_id,{**current,'stage':'parsing'})
            evidence=parse_document(path.read_bytes(),p['filename'])
            with db.Session.begin() as s:
                current=db.get(s,task_id);db.put(s,task_id,{**current,'stage':'extracting'})
            facts=extract_facts(evidence)
        with db.Session.begin() as s:
            current=db.get(s,p['id'],'profile')
            if not current or current['version_id']!=t['profile_version']:raise ValueError('Profile changed during extraction.')
            if not eligibility({**current,'processing_status':'ready'})[0]:raise ValueError('Profile permission or lifecycle changed during extraction.')
            p=db.put(s,p['id'],{**current,'facts':facts,'evidence':evidence,'processing_status':'ready'})
            if not db.get(s,p['version_id']):db.add(s,'profile_version',{'profile_id':p['id'],'facts':facts,'evidence':evidence},p['version_id'])
            if not db.get(s,t['extraction_cache_id']):db.add(s,'extraction_cache',{'document_hash':p['document_hash'],'evidence':evidence,'facts':facts},t['extraction_cache_id'])
            db.add(s,'refresh',{'profile_id':p['id'],'status':'queued'})
            db.audit(s,'extraction_completed',p['id'],'Document extracted with source locations; '+('cached interpretation reused.' if cached else 'new profile version saved.'))
            current=db.get(s,task_id);db.put(s,task_id,{**current,'status':'completed','stage':'completed','reused':bool(cached),'lease_until':0})
        path.unlink(missing_ok=True)
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else 'Document parsing or extraction failed. Supply a valid text-based PDF/DOCX or retry.'
        with db.Session.begin() as s:
            current=db.get(s,task_id)
            if current:db.put(s,task_id,{**current,'status':'failed','error':message[:400],'lease_until':0})
            current=db.get(s,p['id'],'profile')
            if current and current['version_id']==t['profile_version']:db.put(s,p['id'],{**current,'processing_status':'failed'})
