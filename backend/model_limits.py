"""A shared API/worker request gate for NVIDIA trial endpoints (SQLite deployment)."""
import os
import time
from urllib.parse import urlsplit
from sqlalchemy import text
from . import store as db
from .domain import digest


def is_nvidia():
    return urlsplit(os.getenv('LLM_BASE_URL','')).hostname == 'integrate.api.nvidia.com'


def acquire(model):
    if not is_nvidia():
        return None
    rpm = float(os.getenv('LLM_REQUESTS_PER_MINUTE','5'))
    if not 0 < rpm <= 60:
        raise ValueError('LLM_REQUESTS_PER_MINUTE must be between 0 and 60.')
    sid = 'provider_slot_'+digest([os.getenv('LLM_BASE_URL'),model])[:20]
    owner = db.ident('request')
    deadline = time.monotonic()+float(os.getenv('LLM_QUEUE_TIMEOUT_SECONDS','240'))
    timeout = float(os.getenv('LLM_TIMEOUT_SECONDS','180'))
    while True:
        with db.Session() as s:
            s.execute(text('BEGIN IMMEDIATE'))
            slot = db.get(s,sid)
            now = time.time()
            if slot and slot.get('quota_until',0)>now:
                raise ValueError('AI provider rate or quota limit reached (HTTP 429). A shared cooldown is active; wait before retrying in Activity.')
            if not slot or (slot.get('lease_until',0)<=now and slot.get('next_allowed',0)<=now):
                body = {'owner':owner,'lease_until':now+timeout*3+240,'next_allowed':now+60/rpm}
                if slot: db.put(s,sid,{**slot,**body})
                else: db.add(s,'provider_slot',body,sid)
                s.commit()
                return sid,owner
            wait = min(1,max(.1,max(slot.get('lease_until',0),slot.get('next_allowed',0))-now))
            s.rollback()
        if time.monotonic()>=deadline:
            raise ValueError('The AI service is busy with another request. Wait for Activity to finish, then retry.')
        time.sleep(wait)


def release(handle):
    if not handle:return
    with db.Session.begin() as s:
        slot=db.get(s,handle[0])
        if slot and slot.get('owner')==handle[1]:
            db.put(s,slot['id'],{**slot,'lease_until':0,'owner':None})


def cooldown(model, seconds):
    if not is_nvidia():return
    sid='provider_slot_'+digest([os.getenv('LLM_BASE_URL'),model])[:20]
    with db.Session.begin() as s:
        slot=db.get(s,sid)
        if slot:db.put(s,sid,{**slot,'quota_until':time.time()+max(60,seconds)})
