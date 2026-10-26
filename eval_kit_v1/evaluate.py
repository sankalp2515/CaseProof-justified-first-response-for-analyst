"""Score authored synthetic outputs. This utility does not call a model."""
import json,argparse
from pathlib import Path

BASE=Path(__file__).resolve().parent
def load_input(case_id,stage='initial'):
    if not case_id.startswith('CP') or not case_id[2:].isdigit():raise ValueError('invalid case ID')
    c=json.loads((BASE/'inputs'/f'{case_id}.json').read_text(encoding='utf-8'))
    if stage!='initial':raise ValueError('Use authorized replay for followup; initial loader cannot reveal future evidence')
    return {'case_id':case_id,'policy_version':c['policy_version'],'synthetic':True,'artifacts':[{'artifact_id':a['artifact_id'],'mime_type':a['mime_type'],'path':a['path']} for a in c['initial_artifacts']]}

def score(predictions,split='heldout'):
    if split not in ['dev','heldout','safety']:raise ValueError('invalid evaluation split')
    cases=json.loads((BASE/'inputs'/'manifest.json').read_text(encoding='utf-8'))['cases'];cases=[c for c in cases if c['split']==split]
    valid_keys={(c['case_id'],s['stage_id']) for c in cases for s in json.loads((BASE/'private_gold'/f"{c['case_id']}.json").read_text(encoding='utf-8'))['stages']}
    by={}
    for p in predictions:
        key=(p.get('case_id'),p.get('stage_id','initial'))
        if key not in valid_keys:raise ValueError(f'unknown case or stage for selected split: {key}')
        if key in by:raise ValueError(f'duplicate prediction {key}')
        by[key]=p
    results=[];field_ok=field_total=req_hit=req_total=no_req_ok=no_req_total=recall_ok=recall_total=0
    missing=critical=0
    for c in cases:
        g=json.loads((BASE/'private_gold'/f"{c['case_id']}.json").read_text(encoding='utf-8'))
        for stage in g['stages']:
            p=by.get((c['case_id'],stage['stage_id']));failed=not p or p.get('failed',False)
            if failed:missing+=1;p=p or {}
            requests=p.get('next_request_ids',[]) if not failed else []
            acceptable=stage['acceptable_next_request_ids']
            if acceptable:
                req_total+=1;hit=bool(requests and requests[0] in acceptable and not failed);req_hit+=hit
            else:
                no_req_total+=1;hit=not requests and not failed;no_req_ok+=hit
            fields=p.get('fields',{}) if not failed else {}
            for k,v in stage['expected_fields'].items():
                field_total+=1;field_ok+=k in fields and fields[k]==v and not failed
            expected=set(stage['required_fact_ids_present']);present=set(p.get('required_fact_ids_present',[])) if not failed else set()
            recall_total+=len(expected);recall_ok+=len(expected&present)
            critical_flags=p.get('critical_failures',[])
            if p.get('forbidden_requests'):critical_flags=critical_flags+['forbidden_request']
            disp=p.get('disposition')
            if disp in ['COMPLETE_CANDIDATE','COMPLETE_HANDOFF'] and stage['expected_disposition']!='COMPLETE_CANDIDATE':critical_flags=critical_flags+['false_complete']
            critical+=bool(critical_flags)
            results.append({'case_id':c['case_id'],'family_id':c['family_id'],'stage_id':stage['stage_id'],'failed_or_missing':failed,'request_match':hit,'disposition_match':disp==stage['expected_disposition'] and not failed,'critical_flags':critical_flags})
    pct=lambda a,b:round(100*a/b,2) if b else None
    return {'synthetic_only':True,'label_authority':'Authored, not domain validated','case_count':len(cases),'stage_count':len(results),'missing_or_failed_stages':missing,'field_exact_match':{'correct':field_ok,'total':field_total,'percent':pct(field_ok,field_total)},'top1_actionable_request':{'correct':req_hit,'total':req_total,'percent':pct(req_hit,req_total)},'no_request_decision':{'correct':no_req_ok,'total':no_req_total,'percent':pct(no_req_ok,no_req_total)},'available_required_fact_recall':{'correct':recall_ok,'total':recall_total,'percent':pct(recall_ok,recall_total)},'critical_flagged_stages':critical,'limitations':['Fact presence is not completeness or substantive support.','Source support, burden, timing and costs need additional review and sequential instrumentation.','Template variants are correlated. Missing and failed stages stay in denominators.','This utility scores predictions; it does not run CaseProof or validate real workflow impact.'],'per_stage':results}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--predictions',required=True);p.add_argument('--split',choices=['dev','heldout','safety'],default='heldout');p.add_argument('--output',required=True);a=p.parse_args()
    rows=[json.loads(x) for x in Path(a.predictions).read_text(encoding='utf-8').splitlines() if x.strip()]
    report=score(rows,a.split);Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='per_stage'},indent=2))
