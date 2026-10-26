import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const out=fileURLToPath(new URL('../../var/journey-validation/', import.meta.url)),checks=[];
const browser=await chromium.launch({headless:true,args:['--disable-gpu','--disable-dev-shm-usage']});
const context=await browser.newContext({reducedMotion:'reduce'}),page=await context.newPage();
const base='http://127.0.0.1:8188',errors=[];page.on('pageerror',e=>errors.push(e.message));
const check=(name,ok=true)=>{assert.ok(ok,name);checks.push(name);console.log('PASS',name);};
try{
  for(const [width,height] of [[1265,889],[1440,1000],[768,1000],[390,844]]){
    await page.setViewportSize({width,height});const response=await page.goto(base+'/');
    check('Built nginx landing returns 200 at '+width,response.status()===200);
    await page.getByRole('heading',{name:'The whole case. A justified first response.'}).waitFor();
    await page.screenshot({path:path.join(out,'built-landing-'+width+'.png')});
    check('Built landing fits '+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  }
  await page.keyboard.press('Tab');check('Keyboard reaches skip link',await page.getByRole('link',{name:'Skip to content',exact:true}).evaluate(e=>e===document.activeElement));
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();
  check('Mobile navigation exposes analyst workspace',await page.locator('#mobile-nav').getByRole('link',{name:'Analyst workspace',exact:true}).isVisible());
  const links=await page.getByRole('link',{name:'Explore a practice case',exact:true}).all();
  check('All practice CTAs open actual reporting',(await Promise.all(links.map(l=>l.getAttribute('href')))).every(x=>x==='/app/#/victim/start'));
  await page.setViewportSize({width:1265,height:889});
  const money=page.getByRole('tab',{name:'Money Trail',exact:true});await money.focus();await money.press('ArrowRight');
  check('Illustration tabs support arrow keys',await page.getByRole('tab',{name:'Review & handoff',exact:true}).getAttribute('aria-selected')==='true');
  await page.goto(base+'/app/#/victim/start');
  await page.getByRole('button',{name:'Tour',exact:true}).click();
  await page.getByRole('heading',{name:'Welcome: the golden hour',exact:true}).waitFor();
  check('Tour focuses its heading',await page.locator('#tour-title').evaluate(e=>e===document.activeElement));
  await page.keyboard.press('Escape');check('Escape closes tour',await page.locator('.tour-card').count()===0);
  check('Actual demo configuration loads',(await context.request.get(base+'/v1/ui-config')).status()===200);
  check('No browser errors',errors.length===0);
  await fs.writeFile(path.join(out,'built-visual.json'),JSON.stringify({checks,errors},null,2));
}finally{await browser.close();}
