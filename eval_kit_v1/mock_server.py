"""Loopback-only fictional bank support console. No AI and no real banking APIs."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import json,argparse,uuid,threading

BASE=Path(__file__).resolve().parent
MANIFEST=json.loads((BASE/'inputs'/'manifest.json').read_text(encoding='utf-8'))
CASES={x['case_id']:x for x in MANIFEST['cases']}
LEDGER={x['case_id']:x for x in json.loads((BASE/'mock_bank'/'ledger.json').read_text(encoding='utf-8'))}
CATALOGUE=json.loads((BASE/'policy'/'demo_policy_v1.json').read_text(encoding='utf-8'))['request_catalogue']
TICKETS={};REVEALED=set();LOCK=threading.Lock()

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,obj,status=200):
    b=json.dumps(obj,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def body(self):
    size=int(self.headers.get('Content-Length','0'))
    if size>100000:raise ValueError('body too large')
    return json.loads(self.rfile.read(size) or b'{}')
 def do_GET(self):
    u=urlparse(self.path);q=parse_qs(u.query)
    if u.path=='/':
        b=(BASE/'support_console.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
    if u.path=='/health':return self.reply({'ok':True,'synthetic':True,'ai_implemented':False})
    if u.path=='/catalog':return self.reply([{'case_id':c,'family_id':v['family_id'],'scenario':v['scenario'],'split':v['split']} for c,v in CASES.items()])
    if u.path=='/case':
        cid=q.get('id',[''])[0];c=CASES.get(cid)
        if not c:return self.reply({'error':'unknown case'},404)
        stage=q.get('stage',['initial'])[0]
        if stage not in ['initial','followup']:return self.reply({'error':'invalid stage'},422)
        if stage=='followup' and cid not in REVEALED:return self.reply({'error':'followup not revealed'},403)
        return self.reply({'case_id':cid,'synthetic':True,'stage':stage,'artifacts':c['initial_artifacts'] if stage=='initial' else c['followup_artifacts'],'request_catalogue':CATALOGUE,'note':'No labels or AI outputs are served.'})
    if u.path=='/ledger':
        cid=q.get('id',[''])[0]
        return self.reply(LEDGER[cid]) if cid in LEDGER else self.reply({'error':'unknown case'},404)
    if u.path=='/artifact':
        cid=q.get('case',[''])[0];aid=q.get('id',[''])[0];c=CASES.get(cid)
        if not c:return self.reply({'error':'unknown case'},404)
        permitted=c['initial_artifacts']+(c['followup_artifacts'] if cid in REVEALED else [])
        item=next((x for x in permitted if x['artifact_id']==aid),None)
        if not item:return self.reply({'error':'artifact unavailable'},404)
        p=(BASE/item['path']).resolve()
        if not p.is_relative_to((BASE/'fixtures').resolve()):return self.reply({'error':'invalid path'},400)
        b=p.read_bytes();self.send_response(200);self.send_header('Content-Type',item['mime_type']);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
    if u.path=='/tickets':return self.reply(list(TICKETS.values()))
    return self.reply({'error':'route not found'},404)
 def do_POST(self):
    try:data=self.body()
    except Exception:return self.reply({'error':'invalid JSON or body size'},400)
    cid=data.get('case_id');c=CASES.get(cid)
    if self.path=='/reset':
        with LOCK:REVEALED.clear();TICKETS.clear()
        return self.reply({'reset':True,'synthetic':True})
    if not c:return self.reply({'error':'unknown case'},404)
    if self.path=='/reveal':
        rid=data.get('request_id')
        if rid not in CATALOGUE:return self.reply({'error':'not a permitted demo request'},422)
        g=json.loads((BASE/'private_gold'/f'{cid}.json').read_text(encoding='utf-8'))
        allowed=g['stages'][0]['acceptable_next_request_ids']
        if rid not in allowed:return self.reply({'case_id':cid,'available':False,'synthetic':True,'note':'The simulated customer has no response artifact for this request.'})
        with LOCK:REVEALED.add(cid)
        return self.reply({'case_id':cid,'available':True,'synthetic':True,'artifacts':c['followup_artifacts']})
    if self.path=='/tickets':
        if data.get('human_approved') is not True:return self.reply({'error':'human approval required in this simulator'},422)
        if data.get('disposition') not in ['COMPLETE_HANDOFF','ESCALATE_WITH_GAPS']:return self.reply({'error':'invalid disposition'},422)
        if not isinstance(data.get('approved_revision'),int) or data['approved_revision']<1:return self.reply({'error':'revision required'},422)
        key=self.headers.get('Idempotency-Key')
        if not key or len(key)>200:return self.reply({'error':'bounded Idempotency-Key required'},422)
        with LOCK:
            if key in TICKETS:
                old=TICKETS[key]
                if old['case_id']!=cid or old['approved_revision']!=data['approved_revision'] or old['disposition']!=data['disposition']:return self.reply({'error':'idempotency key reused for different ticket'},409)
                return self.reply(old)
            item={'ticket_id':'SYNTH-TICKET-'+uuid.uuid4().hex[:10],'case_id':cid,'approved_revision':data['approved_revision'],'disposition':data['disposition'],'synthetic':True,'status':'received_by_fictional_support','official_report':False}
            TICKETS[key]=item
        return self.reply(item,201)
    return self.reply({'error':'route not found'},404)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--port',type=int,default=8765);args=a.parse_args()
    print(f'Fictional support console http://127.0.0.1:{args.port} - synthetic only, no AI',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
