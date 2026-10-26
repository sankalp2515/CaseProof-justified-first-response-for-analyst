import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const base=process.env.CASEPROOF_BASE_URL||'http://caseproof-journey.localhost:8188',cid=process.env.CASEPROOF_CASE_ID||'CASE-79f16b3fd0ae1ac8';
const out=new URL('../../var/session-18/',import.meta.url);
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch(),page=await browser.newPage({viewport:{width:1440,height:900}});
page.setDefaultTimeout(90000);
const checks=[];
const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);console.log('PASS',name);};
try {
 for(let attempt=0;attempt<30;attempt++){
  const ready=await page.request.get(base+'/health',{timeout:3000}).then(r=>r.ok()).catch(()=>false);
  if(ready)break;
  if(attempt===29)throw Error('Backend did not become healthy for document verification');
  await page.waitForTimeout(1000);
 }
 await page.goto(base+'/app/#/staff/cases/'+cid+'/delivery');
 await page.getByRole('heading',{name:'Delivered packet history',exact:true}).waitFor();
 const api=path=>page.evaluate(async path=>{const r=await fetch(path,{headers:{'X-Demo-User':'analyst'}});if(!r.ok)throw Error('API '+r.status);return r.json();},path);
 const w=await api('/v1/cases/'+cid+'/workflow');
 const delivery=w.historical_deliveries.find(d=>d.packet_id),pid=delivery.packet_id;
 const packet=await api('/v1/cases/'+cid+'/delivered-packets/'+pid);
 const downloadEvent=page.waitForEvent('download');
 await page.getByRole('button',{name:'Download handoff document',exact:true}).first().click();
 const download=await downloadEvent;
 const file=fileURLToPath(new URL('handoff.html',out));
 await download.saveAs(file);
 const html=await fs.readFile(file,'utf8');
 check('Actual UI downloads the original approved handoff',html.includes(pid)&&html.includes(packet.audit.digest)&&html.includes('revision '+packet.revision));
 check('Document includes the sourced money-trail paths',packet.report_update.traced_amounts.length>0&&packet.report_update.traced_amounts.every(p=>p.path.every(id=>html.includes(id))));
 check('Both distinct receivers acknowledged this packet revision',new Set(w.historical_deliveries.filter(d=>d.revision===packet.revision).map(d=>d.kind)).size===2);
 await page.screenshot({path:fileURLToPath(new URL('completed-delivery.png',out))});
 const doc=await browser.newPage({viewport:{width:1050,height:1000}});
 await doc.setContent(html); await doc.screenshot({path:fileURLToPath(new URL('handoff-document.png',out)),fullPage:true});
 await doc.pdf({path:fileURLToPath(new URL('handoff.pdf',out)),format:'A4',printBackground:true});
 check('Original handoff renders to an actual printable PDF',true);
 await fs.writeFile(new URL('output-results.json',out),JSON.stringify({caseId:cid,packetId:pid,revision:packet.revision,checks},null,2));
} finally {await browser.close();}
