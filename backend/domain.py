"""Pure scoring, eligibility, dates and counterfactuals; no network calls."""
import calendar
import hashlib
import itertools
import json
import re
from datetime import date, datetime, timezone

SOURCES = ['current_applicant', 'past_applicant', 'employee']
CREDITS = {'supported': 1.0, 'partial': .5, 'not_evidenced': 0., 'unmet': 0.}

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def parsedate(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError):
        return None

def add_months(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def eligibility(profile, job=None, today=None, pools=None):
    today = today or datetime.now(timezone.utc).date()
    if pools is not None and profile['source_type'] not in pools:
        return False, 'Pool access restricted'
    if profile.get('processing_status','ready') != 'ready':
        return False, 'Profile extraction is pending or failed'
    if profile.get('deleted') or profile.get('suppressed'):
        return False, 'Suppressed from matching'
    if not profile.get('matching_allowed'):
        return False, 'Matching permission not enabled'
    expiry = parsedate(profile.get('retention_expires_at'))
    if not expiry or today >= expiry:
        return False, 'Retention expired or not supplied'
    source = profile['source_type']
    if source == 'past_applicant':
        if profile.get('application_status') != 'rejected':
            return False, 'Only rejected applications enter rediscovery'
        if profile.get('active_interview'):
            return False, 'Approved or interviewing for another role'
        rejected = parsedate(profile.get('rejected_at'))
        if not rejected or rejected > today:
            return False, 'Valid rejection date required'
        if today >= add_months(rejected, 3):
            return False, 'Three-month rediscovery window expired'
    if source == 'employee':
        if not profile.get('internal_visibility', False):
            return False, 'Employee has not opted in to visibility'
        if job and not job.get('internal'):
            return False, 'Job is not open to internal candidates'
    if source == 'current_applicant' and job and profile.get('job_id') != job['id']:
        return False, 'Application belongs to a different job'
    return True, 'Eligible'

def term_in(term, text):
    return bool(term.strip()) and bool(re.search(r'(?<!\w)' + re.escape(term.strip()) + r'(?!\w)', text, re.I))

def month_index(value, today=None):
    today = today or date.today()
    if value and value.lower() == 'present':
        return today.year * 12 + today.month - 1
    if not value or not re.fullmatch(r'\d{4}-\d{2}', value):
        return None
    y, m = map(int, value.split('-'))
    return y * 12 + m - 1 if 1 <= m <= 12 else None

def union_months(roles, today=None):
    intervals = []
    for r in roles:
        a, b = month_index(r.get('start'), today), month_index(r.get('end'), today)
        if a is not None and b is not None and a <= b:
            intervals.append((a, b + 1))
    if not intervals:
        return None
    total, left, right = 0, *sorted(intervals)[0]
    for a, b in sorted(intervals)[1:]:
        if a <= right:
            right = max(right, b)
        else:
            total += right - left
            left, right = a, b
    return total + right - left

def consistency(facts, today=None):
    today = today or date.today()
    current = month_index('present', today)
    flags, seen = [], {}
    for r in facts.get('roles', []):
        a, b = month_index(r.get('start')), month_index(r.get('end'), today)
        if a is not None and b is not None and a > b:
            flags.append(f"{r['title']}: end date precedes start date.")
        if b is not None and b > current and r.get('end') != 'present':
            flags.append(f"{r['title']}: completed role extends into the future.")
        rid = r['id']
        dates = (r.get('start'), r.get('end'))
        if rid in seen and seen[rid] != dates:
            flags.append(f"{r['title']}: conflicting dates for the same role.")
        seen[rid] = dates
    roles = facts.get('roles', [])
    total = union_months(roles, today)
    if roles and all(month_index(r.get('start')) is not None and month_index(r.get('end'), today) is not None for r in roles):
        stated = facts.get('stated_months')
        if stated is not None and total is not None and abs(stated - total) > 12:
            flags.append('Stated total experience differs from fully dated intervals by over 12 months.')
    return flags

def content_key(criteria):
    # A weight-only edit reuses interpretations, but gets a new arithmetic record.
    return digest([{k: v for k, v in c.items() if k not in ('weight', 'enabled')} for c in criteria])

def overlaps(criteria):
    found = []
    for a, b in itertools.combinations(criteria, 2):
        if not a.get('enabled', True) or not b.get('enabled', True):
            continue
        ta = {t.lower() for t in a.get('terms', [])}
        tb = {t.lower() for t in b.get('terms', [])}
        if a['requirement'].lower().strip() == b['requirement'].lower().strip() or (ta and tb and (ta <= tb or tb <= ta)):
            found.append(f"{a['requirement']} / {b['requirement']}")
    return found

def score(criteria, items, evidence, facts=None):
    active = [c for c in criteria if c.get('enabled', True) and c['weight'] > 0]
    total = sum(c['weight'] for c in active)
    if total <= 0:
        raise ValueError('At least one enabled positive weight is required')
    byid = {i['criterion_id']: i for i in items}
    evid = {e['id']: e for e in evidence}
    if len(byid) != len(items) or set(byid) != {c['id'] for c in criteria}:
        raise ValueError('Assessment must contain each rubric criterion exactly once')
    rows, raw, coverage = [], 0., 0.
    essentials = {k: 0 for k in CREDITS}
    for c in active:
        i = byid[c['id']]
        if i['status'] not in CREDITS:
            raise ValueError('Invalid assessment status')
        refs = i.get('evidence_ids', [])
        if any(e not in evid for e in refs):
            raise ValueError('Evidence reference does not resolve')
        if i['status'] != 'not_evidenced' and not refs:
            raise ValueError('Assessable claims require source evidence')
        roles_byid={r['id']:r for r in (facts or {}).get('roles',[])}
        if facts is not None and any(rid not in roles_byid for rid in i.get('role_ids',[])):
            raise ValueError('Assessment role reference does not resolve')
        credit = CREDITS[i['status']]
        if c.get('required_months'):
            if facts is not None and i.get('months') is not None:
                supported_roles=[roles_byid[rid] for rid in i.get('role_ids',[]) if set(roles_byid[rid].get('evidence_ids',[])) & set(refs)]
                ceiling=union_months(supported_roles)
                if ceiling is None:
                    i={**i,'months':None}
                elif i['months']>ceiling:
                    raise ValueError('Claimed relevant months exceed the source-linked dated intervals')
            credit = min(max(i.get('months') or 0, 0) / c['required_months'], 1.)
            if i.get('months') is None:
                i = {**i, 'status': 'not_evidenced', 'rationale': 'Relevant duration is unclear. Ask which dated roles or projects involved this work. A different job title does not rule out relevant experience.'}
            else:
                i = {**i, 'status': 'supported' if credit == 1 else ('partial' if credit > 0 else 'unmet')}
        if c.get('recency_months'):
            used = month_index(i.get('last_used'))
            if used is None:
                credit = 0
                i = {**i, 'status': 'not_evidenced', 'rationale': 'Last use is unclear; the approved recency condition needs evidence.'}
            elif month_index('present') - used > c['recency_months']:
                credit = 0
                i = {**i, 'status': 'unmet', 'rationale': 'Last evidenced use does not meet the approved recency condition.'}
        w = c['weight'] / total
        contribution = 100 * w * credit
        raw += contribution
        if i['status'] != 'not_evidenced':
            coverage += 100 * w
        if c['essential']:
            essentials[i['status']] += 1
        rows.append({**i, 'requirement': c['requirement'], 'category': c['category'], 'essential': c['essential'], 'credit': credit, 'normalized_weight': w, 'contribution': contribution, 'potential_increase': 100 * w * (1-credit), 'full_credit': c['full_credit']})
    skillrows = [r for r in rows if r['category'] == 'skill']
    text = '\n'.join(e['text'] for e in evidence)
    skillweight = sum(r['normalized_weight'] for r in skillrows)
    baseline = contextual = 0.
    recovered = []
    for r in skillrows:
        c = next(c for c in criteria if c['id'] == r['criterion_id'])
        terms = c.get('terms') or [c['requirement']]
        exact = all(any(term_in(x, text) for x in [t] + c.get('equivalents', [])) for t in terms)
        baseline += r['normalized_weight'] * int(exact)
        contextual += r['normalized_weight'] * r['credit']
        if not exact and r['credit'] > 0:
            recovered.append(r['requirement'])
    base = 100 * baseline / skillweight if skillweight else 0
    ctx = 100 * contextual / skillweight if skillweight else 0
    strength = max(rows, key=lambda r:r['contribution'])
    gaps = sorted([r for r in rows if r['credit'] < 1], key=lambda r:(not r['essential'], -r['potential_increase']))
    gap = gaps[0]['requirement'] if gaps else 'No documented gaps'
    relevant_ids = {rid for r in rows for rid in r.get('role_ids', [])}
    relevant_months = union_months([r for r in (facts or {}).get('roles', []) if r['id'] in relevant_ids])
    return {'overall_score': int(raw + .5), 'raw_score': raw, 'coverage': int(coverage+.5), 'essentials': essentials, 'results': rows, 'strength': strength['requirement'] if strength['credit'] else 'No supported criteria yet', 'gap': gap, 'summary': ((f"The resume provides evidence for {strength['requirement']}. " if strength['credit'] else "No requirement has enough supporting evidence yet. ") + ("Discuss with the candidate: " + gap + "." if gaps else "All assessed requirements are supported.")), 'exact_coverage': round(base), 'contextual_coverage': round(ctx), 'overlooked': ctx-base >= 20-1e-9 and bool(recovered), 'overlooked_reasons': recovered, 'relevant_months': relevant_months}

def scenarios(assessment, target):
    rows = sorted([r for r in assessment['results'] if r['credit'] < 1], key=lambda r:(-r['potential_increase'], r['criterion_id']))
    raw = assessment['raw_score']
    best = None
    if raw >= target:
        best = []
    else:
        for n in range(1, 4):
            options = [c for c in itertools.combinations(rows, n) if raw + sum(r['potential_increase'] for r in c) >= target-1e-9]
            if options:
                best = min(options, key=lambda c:(raw+sum(r['potential_increase'] for r in c)-target, sorted(r['criterion_id'] for r in c)))
                break
    return {'target': target, 'current_score': assessment['overall_score'], 'top_gaps': rows[:3], 'combination': None if best is None else list(best), 'hypothetical_score': None if best is None else round(raw + sum(r['potential_increase'] for r in best), 2), 'message': 'Evidence scenario only. No change to the official assessment.'}
