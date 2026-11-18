// Use the existing Playwright runtime. All images are synthetic, never patient data.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const target=process.env.MSH_PHYSICIAN_HTML||path.resolve(__dirname,'../tools/physician_review/MSH_醫師快速分類工具.html');
const results=[];let browser;
async function test(name,fn){try{await fn();results.push({name,status:'PASS'});console.log('PASS',name)}catch(e){results.push({name,status:'FAIL',error:e.stack});console.error('FAIL',name,e.message)}}
(async()=>{
 const work=await fs.mkdtemp(path.join(os.tmpdir(),'msh-yolo-test-'));
 browser=await chromium.launch({channel:process.env.MSH_TEST_BROWSER||'chrome',headless:true});
 const context=await browser.newContext({acceptDownloads:true});
 const requests=[],errors=[];
 await context.route(/https?:\/\//,route=>{requests.push(route.request().url());return route.abort()});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.goto(pathToFileURL(target).href);
 const pixels=await page.evaluate(()=>Array.from({length:4},(_,i)=>{
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
  const ctx=canvas.getContext('2d');ctx.fillStyle=['#ccbbaa','#aaccee','#eeccaa','#bbffaa'][i];ctx.fillRect(0,0,640,480);
  ctx.fillStyle='#432143';ctx.fillRect(100+i*10,50,200,100);
  return canvas.toDataURL(i===3?'image/jpeg':'image/png').split(',')[1];
 }));
 const source=path.join(work,'source');const names=['Case01/001.png','Case02/001.png','different.png','photo.jpg'];
 for(let i=0;i<names.length;i++){const dest=path.join(source,names[i]);await fs.mkdir(path.dirname(dest),{recursive:true});await fs.writeFile(dest,Buffer.from(pixels[i],'base64'))}
 const before=await Promise.all(names.map(async n=>crypto.createHash('sha256').update(await fs.readFile(path.join(source,n))).digest('hex')));
 await page.locator('#folder').setInputFiles(source);await page.waitForFunction(()=>!loading&&files.length===4);
 await page.evaluate(()=>{
  const choices=[['G','G05'],['R','R18'],['P','P04'],['G','G10']];
  [...records.values()].forEach((r,i)=>{r.annotations=[{annotationId:'box-'+i,...classValue(...choices[i]),xMin:100,yMin:50,xMax:300,yMax:150,reviewStatus:'unreviewed',annotator:'test',annotationTimestamp:'2026-10-21T00:00:00Z'}]});
 });
 const initial=await page.evaluate(()=>snapshot());
 async function reset(){await page.evaluate(data=>{records=new Map(data.images.map(r=>[r.relativePath,clone(r)]))},initial)}
 await test('Fixed 61 IDs, G05=4/R18=30/P04=35, normalized original-pixel boxes, distinct split groups',async()=>{
  const p=await page.evaluate(()=>{const p=yoloPlan();return {classes:p.definitions,counts:p.counts,samples:p.samples.map(s=>({line:s.lines[0],image:s.imagePath,label:s.labelPath,split:s.split,sha:s.record.sha256}))}});
  assert.equal(p.classes.length,61);assert.deepEqual(p.classes.map(c=>c.id),Array.from({length:61},(_,i)=>i));
  assert.equal(p.classes.find(c=>c.classCode==='G05').id,4);assert.equal(p.classes.find(c=>c.classCode==='R18').id,30);assert.equal(p.classes.find(c=>c.classCode==='P04').id,35);
  assert.deepEqual(p.counts,{train:3,val:1,boxes:4});
  for(const s of p.samples){const v=s.line.split(' ').map(Number);assert.ok(Math.abs(v[1]-.3125)<1e-10);assert.ok(Math.abs(v[2]-100/480)<1e-10);assert.ok(Math.abs(v[3]-.3125)<1e-10);assert.ok(Math.abs(v[4]-100/480)<1e-10)}
  assert.equal(new Set(p.samples.map(s=>s.label)).size,4);
 });
 await test('Image-level class without boxes is excluded, never turned into a full-image box or negative',async()=>{
  await page.evaluate(()=>{const r=[...records.values()][0];r.annotations=[];r.imageClassification=classValue('G','G05')});
  const p=await page.evaluate(()=>{const p=yoloPlan();return {count:p.samples.length,excluded:p.excluded}});
  assert.equal(p.count,3);assert.equal(p.excluded.length,1);
  await page.evaluate(()=>{for(const r of records.values())r.annotations=[]});
  assert.match(await page.evaluate(()=>{try{yoloPlan()}catch(e){return e.message}}),/請先框選/);
  await reset();
 });
 await test('Reject corrupt boxes, unknown classes, missing hashes and invalid dimensions',async()=>{
  for(const problem of ['box','class','hash','dimension']){
   await reset();await page.evaluate(problem=>{const r=[...records.values()][0];if(problem==='box')r.annotations[0].xMax=100;if(problem==='class')r.annotations[0].classCode='G99';if(problem==='hash')r.sha256='';if(problem==='dimension')r.imageWidth=0},problem);
   assert.equal(await page.evaluate(()=>{try{yoloPlan();return false}catch{return true}}),true,problem);
  }
  await reset();
 });
 await test('Identical files stay in one split; conflicting labels and a single unique image are rejected',async()=>{
  await page.evaluate(async()=>{const original=files[0].file;const duplicate=new File([await original.arrayBuffer()],'copy.png',{type:'image/png'});files.push({file:duplicate,relativePath:'copy.png'});const r=clone(records.get(files[0].relativePath));r.fileName='copy.png';r.relativePath='copy.png';r.annotations[0].annotationId='copy-box';records.set('copy.png',r)});
  const samples=await page.evaluate(()=>yoloPlan().samples.map(s=>({sha:s.record.sha256,split:s.split})));
  assert.equal(samples.length,5);const groups=new Map();for(const s of samples){if(groups.has(s.sha))assert.equal(groups.get(s.sha),s.split);groups.set(s.sha,s.split)}
  await page.evaluate(()=>records.get('copy.png').annotations[0].xMin=90);
  assert.match(await page.evaluate(()=>{try{yoloPlan()}catch(e){return e.message}}),/相同原圖/);
  await page.evaluate(()=>{records.get('copy.png').annotations[0].xMin=100;files=files.filter(f=>f.relativePath==='copy.png'||f.relativePath==='Case01/001.png');records=new Map([...records].filter(([key])=>files.some(f=>f.relativePath===key)))});
  assert.match(await page.evaluate(()=>{try{yoloPlan()}catch(e){return e.message}}),/至少需要兩張/);
  await page.locator('#folder').setInputFiles(source);await page.waitForFunction(()=>!loading&&files.length===4);await reset();
 });
 await test('Real offline ZIP download preserves all original bytes and review state; external validator can read it',async()=>{
  const directory=process.env.MSH_YOLO_TEST_OUTPUT||work;await fs.mkdir(directory,{recursive:true});
  const pending=page.waitForEvent('download');await page.locator('#saveYolo').click();const download=await pending;
  assert.equal(await download.failure(),null);assert.ok(download.suggestedFilename().endsWith('.zip'));
  const output=path.join(directory,'synthetic_yolo_export.zip');await download.saveAs(output);
  const expected=await page.evaluate(()=>yoloPlan().samples.map(s=>({image:s.imagePath,label:s.labelPath,source:s.record.relativePath,sha256:s.record.sha256,lines:s.lines})));
  await fs.writeFile(path.join(directory,'expected.json'),JSON.stringify(expected,null,2));
  const after=await Promise.all(names.map(async n=>crypto.createHash('sha256').update(await fs.readFile(path.join(source,n))).digest('hex')));assert.deepEqual(before,after);
  assert.equal(await page.evaluate(()=>[...records.values()].every(r=>r.reviewStatus==='unreviewed'&&r.annotations.every(a=>a.reviewStatus==='unreviewed'))),true);
  assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);console.log('ZIP',output);
 });
 await test('Export detects changed source bytes and batch replacement during packing',async()=>{
  assert.match(await page.evaluate(async()=>{const p=yoloPlan();p.samples[0].file=new File(['different'],'changed.png');try{await yoloZip(p,snapshot())}catch(e){return e.message}}),/SHA-256 不一致/);
  assert.match(await page.evaluate(async()=>{const p=yoloPlan();try{await yoloZip(p,snapshot(),datasetGeneration-1)}catch(e){return e.message}}),/資料夾已變更/);
 });
 if(process.env.MSH_YOLO_TEST_OUTPUT)await page.screenshot({path:path.join(process.env.MSH_YOLO_TEST_OUTPUT,'tool.png'),fullPage:true});
 if(process.env.MSH_TEST_REPORT)await fs.writeFile(process.env.MSH_TEST_REPORT,JSON.stringify({target,results,requests,errors},null,2));
 console.log(JSON.stringify({passed:results.filter(r=>r.status==='PASS').length,failed:results.filter(r=>r.status==='FAIL').length}));
 if(results.some(r=>r.status==='FAIL'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
