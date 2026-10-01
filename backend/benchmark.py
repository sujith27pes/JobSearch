"""Independent expected outcomes for the six synthetic work patterns.
Run in a separate process; does not alter the running application's database.
"""
import os
import tempfile
os.environ['JOBSCORE_DATA_DIR']=tempfile.mkdtemp(prefix='jobscore-benchmark-')
os.environ['JOBSCORE_MODE']='demo'
import json
from pathlib import Path
from .seed import seed
from . import store as db
from .intelligence import assess_profile
from .domain import score,eligibility

# Human-authored expectations, not generated from the scoring engine.
EXPECTED=[
 {'Java':'supported','PostgreSQL':'supported','Kubernetes':'supported','Kafka':'supported','Incident response':'supported'},
 {'Java':'supported','PostgreSQL':'supported','Kubernetes':'partial','Kafka':'partial','Incident response':'supported'},
 {'Java':'not_evidenced','PostgreSQL':'not_evidenced','Kubernetes':'supported','Kafka':'not_evidenced','Incident response':'supported'},
 {'Java':'not_evidenced','PostgreSQL':'supported','Kubernetes':'not_evidenced','Kafka':'supported','Incident response':'not_evidenced'},
 {'Java':'supported','PostgreSQL':'supported','Kubernetes':'not_evidenced','Kafka':'not_evidenced','Incident response':'not_evidenced'},
 {'Java':'partial','PostgreSQL':'partial','Kubernetes':'partial','Kafka':'partial','Incident response':'not_evidenced'},
]

def main():
    import time
    seed();start=time.monotonic();correct=total=unsupported=0;errors=[]
    with db.Session() as s:
        criteria=db.get(s,'rubric_demo_1')['criteria']
        ps=db.all_of(s,'profile');job=db.get(s,'job_demo_1')
        for n,p in enumerate(ps):
            items=assess_profile(p,criteria);a=score(criteria,items,p['evidence'],p['facts'])
            for r in a['results']:
                total+=1
                expected=EXPECTED[n%6][r['requirement']]
                correct+=r['status']==expected
                if r['status']!=expected:errors.append({'profile':p['id'],'criterion':r['requirement'],'expected':expected,'observed':r['status']})
                unsupported+=int(r['status']!='not_evidenced' and not r['evidence_ids'])
        report={'mode':'Offline synthetic demonstration, not an AI accuracy claim','profiles':len(ps),'eligible':sum(eligibility(p,job)[0] for p in ps),'criteria_checked':total,'matching_expected':correct,'agreement':correct/total,'unreferenced_assessable_claims':unsupported,'errors':errors,'model_calls':0,'model_tokens':0,'seconds':round(time.monotonic()-start,3),'limitations':['Synthetic fixtures contain six repeating patterns, not a representative recruitment dataset.','AI endpoint, fairness, and real-world hiring accuracy are not evaluated.','Matching may still be semantically incorrect despite a valid evidence reference.']}
    path=Path(__file__).resolve().parents[1]/'docs'/'benchmark-results.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
