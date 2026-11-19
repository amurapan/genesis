/** Browser smoke checks. Exported runner accepts an existing Playwright page. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
export default async ({context})=>{
 const base=process.env.SLED_WEB_URL||'http://127.0.0.1:4173';
 const root=process.env.SLED_REPO||process.cwd();
 const page=await context.newPage();await page.setViewportSize({width:1440,height:1080});
 const errors=[],failures=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.url().startsWith(base)&&r.status()>=400)failures.push(`${r.status()} ${r.url()}`);});
 const pass=(name)=>checks.push(name);
 await mkdir(resolve(root,'docs/images'),{recursive:true});
 await page.goto(base,{waitUntil:'networkidle'});await page.locator('#app').waitFor({state:'visible'});
 assert.match(await page.locator('#app h1').textContent(),/Финансовое расследование/);pass('Workspace loads');
 await page.screenshot({path:resolve(root,'docs/images/workspace.png'),fullPage:true});
 await page.locator('[data-action="next"]').click();assert.equal(await page.locator('.trace-step.current').getAttribute('data-step'),'1');pass('Single-step replay');
 await page.locator('[data-action="reset"]').click();assert.equal(await page.locator('.trace-step.current').count(),0);pass('Replay reset');
 await page.locator('[data-tab="ledger"]').click();assert.equal(await page.locator('.data-table tbody tr').count(),4,'Manual ledger row count');pass('Source ledger rows');
 await page.locator('#ledger-search').fill('cash');assert.equal(await page.locator('.data-table tbody tr').count(),1);pass('Ledger search');
 await page.locator('[data-tab="documents"]').click();
 await page.locator('[data-action="play"]').click();await page.waitForFunction(()=>document.querySelectorAll('.finding').length===2,{},{timeout:15000});pass('Recorded replay reaches real findings');
 assert.equal(await page.locator('.finding').count(),2);
 assert.match(await page.locator('.finding').first().textContent(),/Неверный валютный курс/);
 await page.screenshot({path:resolve(root,'docs/images/findings.png'),fullPage:true});
 await page.locator('.finding').first().locator('[data-proof="ledger:r3"]').click();
 assert.match(await page.locator('#detail-content').textContent(),/4400000/);
 assert.match(await page.locator('#detail-content').textContent(),/2026-12-01/);pass('Evidence resolves to exact public source');
 await page.screenshot({path:resolve(root,'docs/images/evidence.png'),fullPage:false});
 await page.keyboard.press('Escape');assert.equal(await page.locator('dialog[open]').count(),0);pass('Dialog keyboard dismissal');
 const downloadPromise=page.waitForEvent('download');await page.locator('[data-action="download-findings"]').click();const download=await downloadPromise;assert.match(download.suggestedFilename(),/findings.json$/);pass('Findings download');
 const counts=[2,2,0,4];
 for(let i=0;i<4;i++){
  await page.locator('#episode-select').selectOption(String(i));await page.locator('[data-action="finish"]').click();
  assert.equal(await page.locator('.finding').count(),counts[i],`Scenario ${i} finding count`);if(i===2)assert.match(await page.locator('#results').textContent(),/Нарушений не обнаружено/);
 }
 pass('All four public scenarios have correct finding counts');
 await page.locator('[data-tab="ledger"]').click();const before=await page.locator('tbody').textContent();await page.locator('[data-action="page-next"]').click();assert.notEqual(await page.locator('tbody').textContent(),before);pass('Large ledger pagination');
 await page.locator('[data-nav="verification"]').click();await page.locator('.case').first().waitFor({state:'visible'});assert.equal(await page.locator('.case.passed').count(),80);assert.equal(await page.locator('.benchmark-table tbody tr').count(),4);pass('80 acceptance cases and four policy results');
 await page.screenshot({path:resolve(root,'docs/images/verification.png'),fullPage:true});
 await page.locator('[data-check="C01"]').click();assert.match(await page.locator('#detail-content').textContent(),/passed/);await page.keyboard.press('Escape');pass('Acceptance evidence dialog');
 await page.locator('[data-nav="architecture"]').click();await page.locator('.flow-card').first().waitFor({state:'visible'});assert.equal(await page.locator('.flow-card').count(),4,'Architecture card count');pass('Architecture components');
 await page.locator('[data-nav="guide"]').click();await page.locator('.check-row').first().waitFor({state:'visible'});assert.equal(await page.locator('.check-row').count(),4,'Jury guide step count');assert.equal(await page.locator('video').count(),1);pass('Jury instructions and video');
 const pdf=await page.request.get(new URL('assets/presentation.pdf',base).href);assert.equal(pdf.status(),200);pass('Presentation served');
 await page.locator('[data-action="start-guide"]').click();await page.locator('#episode-select').waitFor({state:'visible'});assert.equal(await page.locator('#episode-select').inputValue(),'0');pass('Jury example opens correct episode');
 for(const width of [390,768,1440]){
  await page.setViewportSize({width,height:1000});
  for(const route of ['workspace','verification','architecture','guide']){
   await page.goto(`${base}/#${route}`,{waitUntil:'networkidle'});await page.locator('#app').waitFor({state:'visible'});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Horizontal overflow ${width} ${route}`);
  }
 }
 pass('No horizontal overflow at 390, 768 and 1440 px');
 await page.setViewportSize({width:390,height:844});await page.goto(`${base}/#workspace`,{waitUntil:'networkidle'});await page.locator('#app').waitFor({state:'visible'});await page.locator('[data-action="finish"]').click();
 await page.evaluate(()=>window.scrollTo(0,0));
 await page.screenshot({path:resolve(root,'docs/images/mobile.png'),fullPage:true});pass('Mobile result flow');
 const reportPage=await context.newPage();
 await reportPage.goto(new URL('assets/verification.html',base).href,{waitUntil:'networkidle'});
 assert.equal(await reportPage.evaluate(()=>getComputedStyle(document.body).backgroundColor),'rgb(17, 24, 39)');
 await reportPage.close();pass('Full report stylesheet loads under production CSP');
 assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);pass('No browser errors or failed local resources');
 const result={url:base,passed:checks.length,checks,browser_errors:errors,failed_requests:failures};
 await mkdir(resolve(root,'artifacts'),{recursive:true});await writeFile(resolve(root,'artifacts/web-check.json'),JSON.stringify(result,null,2)+'\n');
 await page.close();return result;
};
