// Explicitly requested Playwright verification. Separate browser; no shared tabs.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const out=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../var/frontend-validation/quality');await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
const page=await context.newPage();const errors=[];
page.on('pageerror',e=>errors.push(e.message));
async function shot(name,url){await page.goto(url);await page.waitForTimeout(1400);await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});console.log('CAPTURE',name);}
try{
 const base=process.env.STUDIO_URL||'http://127.0.0.1:8081';
 const ref=process.env.REFERENCE_URL||'http://127.0.0.1:5175';
 await shot('reference-queue-1440',ref+'/#/');
 await shot('reference-trail-1440',ref+'/#/case/CP-24931/trail');
 await shot('reference-evidence-1440',ref+'/#/case/CP-24931/evidence');
 await shot('reference-overview-1440',ref+'/#/case/CP-24931/overview');
 await shot('reference-victim-1440',ref+'/#/portal/CP-24931');
 await shot('current-queue-1440',base+'/app/#/staff/queue');
 await shot('current-victim-1440',base+'/app/#/victim/start');
 await page.goto(base+'/app/#/staff/cases/CASE-51e905c9b85a60c4/trail');
 await page.waitForTimeout(1800);await page.screenshot({path:path.join(out,'current-trail-1440.png'),fullPage:true});
 const geometry=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,fonts:document.fonts.status}));
 await fs.writeFile(path.join(out,'browser-checkpoint.json'),JSON.stringify({errors,geometry,scope:'Screenshots only; acceptance separate'},null,2));
 if(errors.length)throw new Error(errors.join('\n'));
}finally{await browser.close();}
