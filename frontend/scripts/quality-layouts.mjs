import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url),out=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../var/frontend-validation/quality');
const report=JSON.parse(await fs.readFile(path.join(out,'acceptance.json'),'utf8')),cid=report.cases.at(-1),base='http://127.0.0.1:8081';
const browser=await chromium.launch({headless:true}),ctx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'}),page=await ctx.newPage(),results=[];
const errors=[];page.on('pageerror',e=>errors.push(e.message));
async function capture(name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});}
async function audit(name){await page.addScriptTag({path:require.resolve('axe-core/axe.min.js')});const violations=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});const geometry=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));results.push({name,geometry,violations});await fs.writeFile(path.join(out,'layout-audits.json'),JSON.stringify(results,null,2));assert.ok(geometry.scroll<=geometry.viewport,name+' overflow');console.log('LAYOUT',name,'AXE',violations.length);}
try{
 const root=await ctx.request.get(base+'/',{maxRedirects:0});assert.equal(root.status(),302);assert.equal(root.headers().location,'/app/');
 for(const [route,location] of [['/app','/app/'],['/customer/invalid_test_capability','/app/#/victim/reply/invalid_test_capability']]){const r=await ctx.request.get(base+route,{maxRedirects:0});assert.equal(r.status(),302);assert.equal(r.headers().location,location);assert.equal(new URL(r.headers().location,base).origin,base);}
 for(const width of [1280,1440]){
  await page.setViewportSize({width,height:900});
  for(const tab of ['overview','evidence','trail','requests','review','delivery','audit']){
   await page.goto(`${base}/app/#/staff/cases/${cid}/${tab}`);await page.locator('.case-body').waitFor({timeout:60000});
   if(tab==='evidence'){const receipt=page.getByRole('button',{name:/^receipt /});if(await receipt.count())await receipt.first().click();await page.locator('.evidence-image img').waitFor({timeout:15000}).catch(()=>{});}
   await capture(`after-${tab}-${width}`);await audit(tab+'-'+width);
  }
 }
 await page.goto(base+'/app/#/staff/queue');await page.getByRole('combobox',{name:'Case scope'}).selectOption('all');await page.locator('.case-link').first().waitFor({timeout:30000});await capture('after-queue-all-1440');await audit('queue-all-1440');
 await page.goto(`${base}/app/#/staff/cases/${cid}/review`);await page.locator('.case-body').waitFor({timeout:60000});await page.getByRole('combobox',{name:'Staff persona'}).selectOption('reviewer');await page.getByRole('textbox',{name:'Reviewer rationale',exact:true}).fill('Keyboard-only dialog verification; no decision submitted.');
 const trigger=page.getByRole('button',{name:'Review urgent referral',exact:true});if(await trigger.isEnabled()){
  await trigger.focus();await page.keyboard.press('Enter');await page.getByRole('dialog').waitFor();await page.keyboard.press('Tab');assert.ok(await page.getByRole('dialog').evaluate(el=>el.contains(document.activeElement)));await page.keyboard.press('Escape');assert.equal(await page.getByRole('dialog').count(),0);assert.ok(await trigger.evaluate(el=>el===document.activeElement));console.log('KEYBOARD focus containment, Escape and restoration passed');
 }
 await page.setViewportSize({width:768,height:844});await page.goto(`${base}/app/#/staff/cases/${cid}/trail`);await page.locator('.case-body').waitFor({timeout:60000});await capture('after-analyst-narrow-768');await audit('analyst-narrow-768');
 for(const width of [390,768]){
  await page.setViewportSize({width,height:844});await page.goto(base+'/app/#/victim/start');await page.locator('.customer-option').first().waitFor();await capture('after-start-'+width);await audit('victim-start-'+width);
  await page.locator('.customer-option').first().click();await page.getByRole('button',{name:'Continue with selected customer'}).click();await page.getByRole('button',{name:'Report a payment scam',exact:true}).waitFor();await capture('after-home-'+width);await audit('victim-home-'+width);
  await page.getByRole('button',{name:'Report a payment scam',exact:true}).click();await page.getByRole('checkbox',{name:/Dispute payment .*-T1$/}).waitFor();await capture('after-report-'+width);await audit('victim-report-'+width);
 }
 await page.goto(base+'/customer/invalid_test_capability');await page.getByText('This link is unavailable or expired. Return to your report for current requests.',{exact:true}).waitFor();await capture('after-invalid-reply-390');await audit('invalid-reply');
 assert.equal(errors.length,0,'No uncaught browser errors');await fs.writeFile(path.join(out,'layout-summary.json'),JSON.stringify({errors,rootRedirect:true,checks:results.length,criticalOrSerious:results.flatMap(r=>r.violations).filter(v=>['critical','serious'].includes(v.impact)).length},null,2));
}finally{await browser.close();}
