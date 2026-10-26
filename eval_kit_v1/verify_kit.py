from pathlib import Path
import json,hashlib,collections
BASE=Path(__file__).resolve().parent
def verify():
    m=json.loads((BASE/'inputs'/'manifest.json').read_text(encoding='utf-8'))
    assert len(m['cases'])==48
    counts=collections.Counter(c['split'] for c in m['cases']);assert counts=={'dev':16,'heldout':20,'safety':12}
    family_splits=collections.defaultdict(set)
    for c in m['cases']:
        family_splits[c['family_id']].add(c['split'])
        assert c['synthetic'] is True
        g=json.loads((BASE/'private_gold'/f"{c['case_id']}.json").read_text(encoding='utf-8'))
        assert g['case_id']==c['case_id'] and g['caller_identity_verified'] is False
        assert g['stages'][0]['stage_id']=='initial'
        for a in c['initial_artifacts']+c['followup_artifacts']:
            p=(BASE/a['path']).resolve();assert p.is_relative_to((BASE/'fixtures').resolve()) and p.is_file()
            assert a['artifact_id'] in g['sources']
        for stage in g['stages']:
            assert stage['expected_disposition'] in ['COMPLETE_CANDIDATE','ESCALATE_CANDIDATE','REVIEW_REQUIRED']
            if stage['expected_disposition']=='COMPLETE_CANDIDATE':assert not stage['unresolved_required_fact_ids']
    assert len(family_splits)==12 and all(len(v)==1 for v in family_splits.values())
    files=json.loads((BASE/'artifact_manifest.json').read_text(encoding='utf-8'))
    for x in files:
        p=BASE/x['path'];assert p.stat().st_size==x['bytes'];assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
    ledger=json.loads((BASE/'mock_bank'/'ledger.json').read_text(encoding='utf-8'));assert len(ledger)==48 and all(x['synthetic'] for x in ledger)
    return {'cases':48,'families':12,'split_counts':dict(counts),'artifact_files':len(files),'hashes_verified':len(files),'ledger_records':len(ledger),'labels_domain_validated':False,'model_benchmark_run':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
