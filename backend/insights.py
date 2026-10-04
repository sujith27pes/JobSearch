"""Descriptive career context and time refreshes. None changes criterion weights."""
import re
from datetime import date
from .domain import month_index, union_months


def refresh_duration(items, facts, previous_date, today):
    """Advance only a previously evidenced full role interval; never a project estimate."""
    rows = [dict(i) for i in items]
    if not previous_date:
        return rows
    old = date.fromisoformat(previous_date)
    roles = {r['id']: r for r in facts.get('roles', [])}
    for row in rows:
        selected = [roles[r] for r in row.get('role_ids', []) if r in roles]
        if selected and any(r.get('end') == 'present' for r in selected):
            if row.get('months') is not None and row['months'] == union_months(selected, old):
                row['months'] = union_months(selected, today)
    return rows


def career_context(profile, today=None):
    today = today or date.today()
    evidence = {e['id']: e for e in profile.get('evidence', [])}
    current = month_index('present', today)
    roles = []
    for r in profile.get('facts', {}).get('roles', []):
        start, end = month_index(r.get('start'), today), month_index(r.get('end'), today)
        months = end-start+1 if start is not None and end is not None and start <= end else None
        scopes = [evidence[e] for e in r.get('evidence_ids', []) if e in evidence and re.search(r'\b(led|managed|mentored|owned|responsible for)\b', evidence[e]['text'], re.I)]
        roles.append({**r, 'documented_months': months, 'scope_evidence': scopes})
    dated = sorted([r for r in roles if month_index(r.get('start')) is not None], key=lambda r: month_index(r['start']))
    changes = []
    for before, after in zip(dated, dated[1:]):
        if before['title'].casefold() != after['title'].casefold():
            changes.append({'from_title': before['title'], 'to_title': after['title'], 'months_between_starts': month_index(after['start'])-month_index(before['start']), 'evidence_ids': after.get('evidence_ids', [])})
    short = [r for r in dated if r.get('end') != 'present' and r['documented_months'] is not None and 0 < r['documented_months'] < 18 and 0 <= current-month_index(r['end']) <= 60]
    overlap = any(month_index(a.get('end'), today) is not None and month_index(a['end'], today) >= month_index(b['start'], today) for a,b in zip(dated, dated[1:]))
    promotions=[]
    for e in evidence.values():
        if not re.search(r'\bpromoted to\b',e['text'],re.I):continue
        if re.search(r'\b(not|never|if)\s+promoted to\b',e['text'],re.I):continue
        matches=re.findall(r'\bpromoted to\b[^.!?\n]{0,100}?\b(?:in|on)\s+(\d{4}-\d{2})|\b(\d{4}-\d{2})\s*[:|–-]?\s*promoted to\b',e['text'],re.I)
        dates=[d for pair in matches for d in pair if d and month_index(d) is not None and month_index(d)<=current]
        # Multiple dates in a passage are ambiguous: expose the claim but withhold timing.
        promotions.append({'text':e['text'],'date':dates[0] if len(set(dates))==1 else None,'evidence_id':e['id']})
    dated_promotions=sorted({p['date'] for p in promotions if p['date']})
    intervals=[month_index(b)-month_index(a) for a,b in zip(dated_promotions,dated_promotions[1:])]
    return {'roles': roles, 'title_changes': changes, 'documented_promotions':promotions, 'promotion_intervals_months':intervals, 'short_completed_roles': short, 'repeated_short_tenures': len(short) >= 3, 'overlapping_roles': overlap, 'note': 'Title changes are not verified promotions. Explicit promotion and scope passages are resume claims. Short tenures do not establish motives or retention risk and never change the score.'}


def skill_freshness(profile, results=None):
    """Expose evidenced use from assessment rows, otherwise dated mentions only."""
    rows = []
    for skill in profile.get('facts', {}).get('skills', []):
        refs = [e for e in profile.get('evidence', []) if re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)', e['text'], re.I)]
        dates = []
        for e in refs:
            dates.extend(d for d in re.findall(r'\b\d{4}-\d{2}\b', e['text']) if month_index(d) is not None)
            if re.search(r'\bpresent\b', e['text'], re.I):
                dates.append('present')
        assessed = [r for r in (results or []) if r.get('category') == 'skill' and any(re.search(r'(?<!\w)'+re.escape(skill)+r'(?!\w)', term, re.I) for term in [r.get('requirement','')]+r.get('terms',[])+r.get('equivalents',[])) and r.get('last_used') and set(r.get('evidence_ids', [])) & {e['id'] for e in refs}]
        used = max((r['last_used'] for r in assessed), default=None)
        rows.append({'skill': skill, 'last_evidenced': used, 'dated_mention': max(dates, default=None), 'evidence_ids': [e['id'] for e in refs], 'label': 'Last evidenced use' if used else 'Dated mention; use not established' if dates else 'Last use unknown'})
    return rows
