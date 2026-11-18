// Run with an existing Playwright installation; no package installation is needed.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const crypto=require('node:crypto');
const {pathToFileURL}=require('node:url');
const target=process.env.MSH_PHYSICIAN_HTML||path.resolve(__dirname,'../tools/physician_review/MSH_醫師快速分類工具.html');
const results=[];
let browser,context,page,fixture,requests=[],exceptions=[];
async function test(name,fn){try{await fn();results.push({name,status:'PASS'});console.log('PASS',name)}catch(e){results.push({name,status:'FAIL',error:e.message});console.error('FAIL',name,e.message)}}
async function waitLoaded(){await page.waitForFunction(()=>!loading&&files.length>0)}
async function selectImage(number){await page.selectOption('#imageList',String(number));await page.waitForFunction(()=>document.querySelector('#image').naturalWidth>0&&!document.querySelector('#image').classList.contains('hidden'))}
async function choose(parent,child){await page.selectOption('#parent',parent);await page.selectOption('#child',child)}
async function enterDrawing(){
 if(await page.evaluate(()=>el.mode.value==='browse'))await page.locator('#startBox').click();
 else if(await page.evaluate(()=>!!selectedId))await page.locator('#newBox').click();
}
async function leaveDrawing(){if(await page.evaluate(()=>el.mode.value==='draw'))await page.locator('#startBox').click();}

async function importPayload(name,content){
 await page.evaluate(()=>say(''));
 await page.locator('#restore').setInputFiles({name,mimeType:name.endsWith('.json')?'application/json':'text/csv',buffer:Buffer.from(content)});
 await page.waitForFunction(()=>/恢復|匯入失敗|已讀取備份/.test(el.message.textContent));
}
async function screenPoint(px,py){return page.evaluate(([px,py])=>{const p=new DOMPoint(px,py).matrixTransform(document.querySelector('#overlay').getScreenCTM());return {x:p.x,y:p.y}},[px,py])}
async function drag(from,to){const a=await screenPoint(...from),b=await screenPoint(...to);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:6});await page.mouse.up()}
async function parseCSV(text){
 // Independent CSV parser in the test, not the application's V1 importer.
 const rows=[];let row=[],v='',quoted=false;
 for(let i=0;i<text.replace(/^\uFEFF/,'').length;i++){
  const t=text.replace(/^\uFEFF/,''),c=t[i];
  if(c==='"'){if(quoted&&t[i+1]==='"'){v+='"';i++}else quoted=!quoted}
  else if(c===','&&!quoted){row.push(v);v=''}
  else if(c==='\n'&&!quoted){row.push(v.replace(/\r$/,''));rows.push(row);row=[];v=''}else v+=c;
 }
 if(v||row.length){row.push(v);rows.push(row)}
 return rows;
}
(async()=>{
 fixture=await fs.mkdtemp(path.join(os.tmpdir(),'msh-physician-test-'));
 browser=await chromium.launch({channel:process.env.MSH_TEST_BROWSER||'chrome',headless:true,downloadsPath:path.join(fixture,'downloads')});
 context=await browser.newContext({viewport:{width:1280,height:1200},acceptDownloads:true});
 await context.route(/https?:\/\//,route=>{requests.push(route.request().url());return route.abort()});
 page=await context.newPage();page.on('pageerror',e=>exceptions.push(e.message));
 await page.goto(pathToFileURL(target).href);
 await test('Single HTML relocation: embedded logo decodes without assets or network; compact controls and collapsed shortcuts',async()=>{
  const portableDir=path.join(fixture,'單一檔案 & 搬移');await fs.mkdir(portableDir);
  const portableFile=path.join(portableDir,'醫師工具.html');await fs.copyFile(target,portableFile);
  assert.deepEqual(await fs.readdir(portableDir),['醫師工具.html']);
  const portable=await context.newPage();await portable.goto(pathToFileURL(portableFile).href);
  await portable.locator('.brand-art').evaluate(img=>img.decode());
  assert.equal(await portable.locator('.brand-art').evaluate(img=>img.naturalWidth),640);
  assert.equal(await portable.locator('.brand-art').evaluate(img=>img.src.startsWith('data:image/png;base64,')),true);
  assert.equal(await portable.locator('#notes,#reviewStatus').count(),0);
  assert.equal(await portable.locator('.shortcut-help').evaluate(e=>e.open),false);
  const captions=await portable.locator('button').allInnerTexts();assert.ok(captions.every(s=>s.trim().length<=10),JSON.stringify(captions));
  assert.equal(await portable.locator('#classify').innerText(),'儲存');
  await portable.close();
 });
 const bytes=await page.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=3088;canvas.height=2064;
  const ctx=canvas.getContext('2d');ctx.fillStyle='#f7e5ef';ctx.fillRect(0,0,3088,2064);ctx.fillStyle='#641153';ctx.fillRect(200,200,400,500);
  return {png:canvas.toDataURL('image/png').split(',')[1],jpeg:canvas.toDataURL('image/jpeg').split(',')[1],webp:canvas.toDataURL('image/webp').split(',')[1]};
 });
 const root=path.join(fixture,'原圖 & 測試');await fs.mkdir(path.join(root,'nested'),{recursive:true});
 for(const [name,type]of [['1.JPG','jpeg'],['2.jpeg','jpeg'],['10.PNG','png'],['nested/20.jpg','jpeg']])await fs.writeFile(path.join(root,name),Buffer.from(bytes[type],'base64'));
 await fs.writeFile(path.join(root,'README.txt'),'not an image');
 const sourcePaths=['1.JPG','2.jpeg','10.PNG','nested/20.jpg'];
 const sourceHashes=await Promise.all(sourcePaths.map(async n=>crypto.createHash('sha256').update(await fs.readFile(path.join(root,n))).digest('hex')));
 await test('Folder picker: four real JPG/JPEG/PNG files, nested path, uppercase, natural order, optional reviewer',async()=>{
  await page.locator('#folder').setInputFiles(root);await waitLoaded();
  assert.deepEqual(await page.evaluate(()=>files.map(f=>f.relativePath)),sourcePaths);
  assert.equal(await page.evaluate(()=>[...records.values()].filter(r=>!r.loadError).length),4);
  assert.match(await page.locator('#loadSummary').innerText(),/找到圖片：4.*成功載入：4.*失敗：0/);
 });
 await test('Image really visible and centered at explicit viewer origin',async()=>{
  const r=await page.evaluate(()=>{const a=el.image.getBoundingClientRect(),v=el.viewer.getBoundingClientRect();return {centerX:a.x+a.width/2,centerY:a.y+a.height/2,vx:v.x+v.width/2,vy:v.y+v.height/2,width:a.width,height:a.height}});
  assert.ok(r.width>100&&r.height>100);assert.ok(Math.abs(r.centerX-r.vx)<2&&Math.abs(r.centerY-r.vy)<2,JSON.stringify(r));
 });
 await test('Compact save and box toggle visible; incomplete category cannot start drawing',async()=>{
  assert.equal(await page.locator('select#mode').count(),0);
  assert.equal(await page.locator('#classify').isVisible(),true);assert.equal(await page.locator('#startBox').isVisible(),true);
  assert.match(await page.locator('#classify').getAttribute('aria-label'),/整張影像/);
  await enterDrawing();assert.equal(await page.evaluate(()=>el.mode.value),'browse');
  assert.match(await page.locator('#message').innerText(),/請先選/);assert.equal(await page.evaluate(()=>current().annotations.length),0);
 });
 await test('Six parents and exact 61 labels (13/19/7/8/8/6); parent change clears child',async()=>{
  assert.deepEqual(await page.evaluate(()=>CLASSIFICATION.map(p=>p.children.length)),[13,19,7,8,8,6]);
  assert.equal(await page.evaluate(()=>classes.size),61);
  for(const p of ['G','R','P','L','M','A']){await page.selectOption('#parent',p);assert.ok((await page.locator('#child option').evaluateAll(nodes=>nodes.slice(1).map(n=>n.value))).every(code=>code.startsWith(p)))}
  await choose('G','G05');await page.selectOption('#parent','R');assert.equal(await page.locator('#child').inputValue(),'');
  await page.locator('#classify').click();assert.equal(await page.evaluate(()=>current().imageClassification),null);
 });
 await test('G10 save, exact labels, image-only CSV row, existing metadata preserved without review controls',async()=>{
  await page.uncheck('#autoNext');await page.fill('#reviewer','test_reviewer');await choose('G','G10');
  await page.locator('#classify').click();
  assert.equal(await page.locator('#notes, #reviewStatus').count(),0);
  const metadata=await page.evaluate(()=>snapshot());metadata.images[0].notes='含逗號, "quote"\n第二行';metadata.images[0].reviewStatus='confirmed';
  await importPayload('existing-metadata.json',JSON.stringify(metadata));
  const data=await page.evaluate(()=>current());assert.equal(data.imageClassification.classCode,'G10');assert.equal(data.imageClassification.classLabel,'Myeloblast/Promyelocyte with Auer rod(s)');assert.equal(data.imageClassification.parentLabel,'GRANULOCYTIC (MYELOID) CELLS');
  const rows=await page.evaluate(()=>csvRows());assert.equal(rows.length,5);assert.equal(rows[1][12],'');assert.equal(rows[1][10],'G10');assert.equal(data.reviewStatus,'confirmed');
 });
 await test('Pointer draw three independent G05/R18/P04 boxes using original pixel coordinates',async()=>{
  await page.locator('#viewer').scrollIntoViewIfNeeded();await enterDrawing();
  for(const [p,c,a,b]of [['G','G05',[200,200],[600,700]],['R','R18',[900,200],[1200,700]],['P','P04',[1600,200],[1900,700]]]){await choose(p,c);await drag(a,b)}
  const boxes=await page.evaluate(()=>current().annotations);assert.equal(boxes.length,3);assert.deepEqual(boxes.map(a=>a.classCode),['G05','R18','P04']);
  assert.ok(Math.abs(boxes[0].xMin-200)<1&&Math.abs(boxes[0].xMax-600)<1);assert.equal(await page.evaluate(()=>current().imageClassification.classCode),'G10');
 });
 await test('Pointer select/move/resize; single-box classification; delete/recreate/undo',async()=>{
  const id=await page.evaluate(()=>current().annotations[0].annotationId);await page.selectOption('#boxes',id);
  await drag([400,450],[500,550]);let box=await page.evaluate(()=>current().annotations[0]);assert.ok(Math.abs(box.xMin-300)<2&&Math.abs(box.yMin-300)<2);
  await drag([box.xMax,box.yMax],[box.xMax+100,box.yMax+100]);box=await page.evaluate(()=>current().annotations[0]);assert.ok(Math.abs(box.xMax-800)<3&&Math.abs(box.yMax-900)<3);
  await page.selectOption('#parent','R');assert.equal(await page.locator('#child').inputValue(),'');await page.selectOption('#child','R05');await page.locator('#classify').click();assert.deepEqual(await page.evaluate(()=>current().annotations.map(a=>a.classCode)),['R05','R18','P04']);
  await page.locator('#deleteBox').click();assert.equal(await page.evaluate(()=>current().annotations.length),2);
  await page.locator('#undo').click();assert.equal(await page.evaluate(()=>current().annotations.length),3);
  await page.locator('#viewer').scrollIntoViewIfNeeded();await choose('G','G05');await drag([2200,1200],[2400,1400]);assert.equal(await page.evaluate(()=>current().annotations.length),4);
  await page.locator('#deleteBox').click();assert.equal(await page.evaluate(()=>current().annotations.length),3);
 });
 await test('Shared classification target: box save stays on image, image/other boxes independent, switch restores image category',async()=>{
  const indexBefore=await page.evaluate(()=>index),imageBefore=await page.evaluate(()=>clone(current().imageClassification));
  await page.selectOption('#boxes',await page.evaluate(()=>current().annotations[1].annotationId));
  assert.equal(await page.locator('#child').inputValue(),'R18');
  assert.equal(await page.locator('#autoNext').isDisabled(),true);
  assert.match(await page.locator('#targetHint').innerText(),/框 #2/);
  assert.match(await page.locator('#classify').getAttribute('aria-label'),/選取框/);
  assert.equal(await page.locator('#drawHint').isVisible(),true);
  await choose('P','P03');await page.locator('#status').click();await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>index),indexBefore);assert.deepEqual(await page.evaluate(()=>current().imageClassification),imageBefore);
  assert.deepEqual(await page.evaluate(()=>current().annotations.map(a=>a.classCode)),['R05','P03','P04']);
  await page.locator('#undo').click();assert.deepEqual(await page.evaluate(()=>current().annotations.map(a=>a.classCode)),['R05','R18','P04']);
  await leaveDrawing();assert.equal(await page.locator('#child').inputValue(),'G10');
  assert.equal(await page.locator('#boxPicker').isVisible(),true);assert.equal(await page.locator('#deleteBox').isVisible(),false);
  assert.equal(await page.locator('#parent').count(),1);assert.equal(await page.locator('#boxParent').count(),0);
  await enterDrawing();
 });
 await test('Explicit new-box action and Escape/navigation clear drawing context without changing image classification',async()=>{
  const before=await page.evaluate(()=>clone(current().imageClassification));
  await choose('M','M02');await enterDrawing();
  assert.match(await page.locator('#drawHint').innerText(),/M02/);
  assert.equal(await page.evaluate(()=>selectedId),null);
  assert.deepEqual(await page.evaluate(()=>current().imageClassification),before);
  await page.locator('#status').click();await page.keyboard.press('Escape');
  assert.equal(await page.evaluate(()=>el.mode.value),'browse');assert.equal(await page.locator('#drawHint').isVisible(),false);
  assert.equal(await page.locator('#child').inputValue(),'G10');
  await enterDrawing();await page.locator('#next').click();
  assert.equal(await page.evaluate(()=>el.mode.value),'browse');assert.match(await page.locator('#classify').getAttribute('aria-label'),/整張影像/);
  await page.locator('#previous').click();
  await enterDrawing();
 });
 await test('Zoom/pan/window resize/devicePixelRatio: stored coordinates stable and SVG aligned',async()=>{
  const before=await page.evaluate(()=>JSON.stringify(current().annotations));
  await page.locator('#zoomIn').click();await page.setViewportSize({width:1000,height:1000});await page.waitForTimeout(150);
  await leaveDrawing();await page.locator('#viewer').scrollIntoViewIfNeeded();await drag([1400,1000],[1450,1050]);
  assert.equal(await page.evaluate(()=>JSON.stringify(current().annotations)),before);
  assert.equal(await page.evaluate(()=>el.image.style.transform===el.overlay.style.transform),true);
  const p=await screenPoint(300,300);const point=await page.evaluate(p=>imagePoint({clientX:p.x,clientY:p.y}),p);assert.ok(Math.abs(point.x-300)<.01&&Math.abs(point.y-300)<.01);
  await page.setViewportSize({width:1280,height:1200});await page.locator('#fit').click();
  const hidpi=await browser.newContext({viewport:{width:1280,height:1200},deviceScaleFactor:2});const hp=await hidpi.newPage();await hp.goto(pathToFileURL(target).href);await hp.locator('#folder').setInputFiles(root);await hp.waitForFunction(()=>!loading&&files.length===4);
  assert.equal(await hp.evaluate(()=>{const p=new DOMPoint(821,442).matrixTransform(el.overlay.getScreenCTM());const q=imagePoint({clientX:p.x,clientY:p.y});return Math.abs(q.x-821)<.01&&Math.abs(q.y-442)<.01}),true);await hidpi.close();
 });
 let backup;
 await test('CSV independently parsed: comma/quote/newline/Unicode, three object rows, image-only records retained',async()=>{
  const csv=await page.evaluate(()=>csvString()),rows=await parseCSV(csv),headers=rows[0];
  assert.ok(rows.every(r=>r.length===headers.length));assert.equal(rows.length,7);
  const objects=rows.slice(1).filter(r=>r[headers.indexOf('annotation_id')]);assert.equal(objects.length,3);
  assert.equal(objects[0][headers.indexOf('object_class_label')],'Fragmented red cell (schistocyte, helmet cell, keratocyte)');
  assert.equal(objects[0][headers.indexOf('notes')],'含逗號, "quote"\n第二行');
  assert.equal(new Set(objects.map(r=>r[headers.indexOf('sha256')])).size,1);assert.equal(new Set(objects.map(r=>r[headers.indexOf('annotation_id')])).size,3);
  await selectImage(1);await choose('G','G05');await page.locator('#classify').click();
  const next=await parseCSV(await page.evaluate(()=>csvString()));const imageOnly=next.find(r=>r[3]==='2.jpeg');assert.equal(imageOnly[10],'G05');assert.equal(imageOnly[12],'');
  backup=await page.evaluate(()=>snapshot());
 });
 await test('SHA-256 equals original bytes; unchanged copy identical; changed same-name file differs',async()=>{
  assert.deepEqual(await page.evaluate(()=>[...records.values()].map(r=>r.sha256)),sourceHashes);
  const checks=await page.evaluate(async()=>{const f=files[0].file,b=await f.arrayBuffer();return [await sha256(f),await sha256(new File([b],f.name)),await sha256(new File([b,'changed'],f.name))]});assert.equal(checks[0],checks[1]);assert.notEqual(checks[0],checks[2]);
 });
 await test('Reload + same folder restores image/box classes, notes, reviewStatus and navigation',async()=>{
  await page.reload();await page.locator('#folder').setInputFiles(root);await waitLoaded();
  const state=await page.evaluate(()=>snapshot());assert.deepEqual(state.images,backup.images);assert.equal(state.currentPath,backup.currentPath);
  await page.locator('#folder').setInputFiles(root);await waitLoaded();assert.deepEqual(await page.evaluate(()=>snapshot().images),backup.images);
 });
 await test('JSON import restores positions; invalid/hash mismatch/missing image records explicitly quarantined',async()=>{
  const text=JSON.stringify(backup);await importPayload('backup.json',text);
  assert.deepEqual(await page.evaluate(()=>snapshot().images),backup.images);
  const changed=structuredClone(backup);changed.images[0].sha256='0'.repeat(64);changed.images[1].relativePath='missing.jpg';changed.images[2].imageClassification={parentCode:'R',classCode:'G05'};
  await importPayload('bad.json',JSON.stringify(changed));
  const reasons=await page.evaluate(()=>unmatchedRecords.map(r=>r.reason));assert.ok(reasons.includes('HASH_MISMATCH'));assert.ok(reasons.includes('MISSING_IMAGE'));assert.ok(reasons.includes('INVALID_CLASSIFICATION'));
 });
 await test('Validation blocks zero/out-of-bounds/duplicate-ID/wrong-parent boxes without silent export',async()=>{
  const result=await page.evaluate(()=>{
   const good=clone([...records.values()][0]),bad=clone(good);bad.annotations[0].xMin=-1;bad.annotations[0].parentCode='P';bad.annotations[1].annotationId=bad.annotations[0].annotationId;bad.annotations[2].xMax=bad.annotations[2].xMin;
   return validateRecord(bad);
  });assert.ok(result.some(e=>e.includes('重複')));assert.ok(result.some(e=>e.includes('不相符')));assert.ok(result.some(e=>e.includes('面積')));
 });
 await test('Corrupt image isolated; empty MIME fallback; real WEBP/BMP decode; TIFF extension retained',async()=>{
  const bmp=Buffer.alloc(54+32*16*3);bmp.write('BM');bmp.writeUInt32LE(bmp.length,2);bmp.writeUInt32LE(54,10);bmp.writeUInt32LE(40,14);bmp.writeInt32LE(32,18);bmp.writeInt32LE(16,22);bmp.writeUInt16LE(1,26);bmp.writeUInt16LE(24,28);bmp.fill(170,54);
  await page.evaluate(async ({webp,bmp})=>{
   const buf=await files[0].file.arrayBuffer(),decode=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
   const list=[new File([buf],'正常.JPG',{type:''}),new File([decode(webp)],'image.WEBP',{type:''}),new File([decode(bmp)],'image.BMP',{type:''}),new File(['bad'],'broken.png'),new File(['tiff-not-supported'],'unknown.TIF'),new File(['text'],'README.txt')];
   await loadFiles(list);
  },{webp:bytes.webp,bmp:bmp.toString('base64')});assert.equal(await page.evaluate(()=>files.length),5);assert.equal(await page.evaluate(()=>[...records.values()].filter(r=>!r.loadError).length),3);assert.equal(await page.evaluate(()=>[...records.values()].filter(r=>r.loadError).length),2);
  assert.deepEqual(await page.evaluate(()=>[records.get('image.BMP').imageWidth,records.get('image.BMP').imageHeight]),[32,16]);
 });
 await test('Duplicate filenames in nested folders remain distinct; V1 labels never guessed; ambiguous fallback reported',async()=>{
  await page.evaluate(async()=>{
   const bytes=await files.find(f=>f.file.name==='正常.JPG').file.arrayBuffer();const list=['Root/Case01/001.jpg','Root/Case02/001.jpg','Root/unique.jpg'].map(p=>{const f=new File([bytes],p.split('/').pop());Object.defineProperty(f,'webkitRelativePath',{value:p});return f});await loadFiles(list);
  });assert.deepEqual(await page.evaluate(()=>files.map(f=>f.relativePath)),['Case01/001.jpg','Case02/001.jpg','unique.jpg']);
  const message=await page.evaluate(()=>restoreData([{image_id:'001.jpg',doctor_category:'Neutrophil'},{image_id:'unique.jpg',doctor_category:'Monocyte'}]));assert.match(message,/AMBIGUOUS_FILENAME/);
  assert.equal(await page.evaluate(()=>records.get('unique.jpg').imageClassification),null);assert.equal(await page.evaluate(()=>records.get('unique.jpg').legacyClassification),'Monocyte');
  const legacyCsv='"reviewer","batch_name","image_id","doctor_category"\r\n"x","b","unique.jpg","WBC_中性球_Neutrophil"';await importPayload('old.csv',legacyCsv);
  assert.equal(await page.evaluate(()=>records.get('unique.jpg').imageClassification),null);assert.equal(await page.evaluate(()=>records.get('unique.jpg').legacyClassification),'WBC_中性球_Neutrophil');
 });
 await test('Auto-next, previous/next/skip, contextual numeric shortcut, Ctrl+Z preserved',async()=>{
  await selectImage(0);await page.check('#autoNext');await choose('G','G05');await page.locator('#classify').click();assert.equal(await page.evaluate(()=>index),1);
  await page.locator('#previous').click();assert.equal(await page.evaluate(()=>index),0);await page.locator('#next').click();assert.equal(await page.evaluate(()=>index),1);
  await page.locator('#skip').click();assert.equal(await page.evaluate(()=>index),2);await choose('R','R04');await page.locator('#status').click();await page.keyboard.press('1');assert.equal(await page.evaluate(()=>current().imageClassification.classCode),'R01');await page.keyboard.press('Control+z');assert.equal(await page.evaluate(()=>current().imageClassification),null);
 });
 await test('Offline CSV/JSON actual downloads; no HTTP requests or JS exceptions',async()=>{
  for(const [id,ext]of [['save','csv'],['saveJson','json']]){const downloadPromise=page.waitForEvent('download');await page.locator('#'+id).click();const d=await downloadPromise;assert.ok(d.suggestedFilename().endsWith('.'+ext));const p=await d.path();assert.ok((await fs.stat(p)).size>100)}
  assert.deepEqual(requests,[]);assert.deepEqual(exceptions,[]);
 });
 await test('All original source image names and byte hashes unchanged after annotation/export',async()=>{
  const after=await Promise.all(sourcePaths.map(async n=>crypto.createHash('sha256').update(await fs.readFile(path.join(root,n))).digest('hex')));assert.deepEqual(after,sourceHashes);assert.deepEqual((await fs.readdir(path.join(root,'nested'))),['20.jpg']);
 });
 await test('localStorage denial clearly warns and JSON backup still works',async()=>{
  const c=await browser.newContext({acceptDownloads:true});const p=await c.newPage();
  await c.route(/https?:\/\//,route=>route.abort());
  await p.addInitScript(()=>{Storage.prototype.setItem=function(){throw new Error('Storage denied for test')}});
  await p.goto(pathToFileURL(target).href);await p.locator('#folder').setInputFiles(root);await p.waitForFunction(()=>!loading&&files.length===4);
  assert.match(await p.locator('#message').innerText(),/自動儲存失敗/);
  const download=p.waitForEvent('download');await p.locator('#saveJson').click();assert.equal(await (await download).failure(),null);await c.close();
 });
 await test('Malformed localStorage is reported and preserved instead of overwritten',async()=>{
  const c=await browser.newContext();const p=await c.newPage();await c.route(/https?:\/\//,route=>route.abort());
  await p.goto(pathToFileURL(target).href);await p.locator('#folder').setInputFiles(root);await p.waitForFunction(()=>!loading&&files.length===4);
  await p.evaluate(()=>localStorage.setItem(storageKey,'{invalid backup'));
  // Avoid the normal unload save, to simulate a previously damaged browser entry.
  await p.evaluate(()=>autoSaveAllowed=false);await p.reload();await p.locator('#folder').setInputFiles(root);await p.waitForFunction(()=>!loading&&files.length===4);
  assert.match(await p.locator('#message').innerText(),/本機恢復失敗/);assert.equal(await p.evaluate(()=>localStorage.getItem(storageKey)),'{invalid backup');await c.close();
 });
 await test('Nonzero tiny box warning, zero-area rejection and out-of-image clamping',async()=>{
  await selectImage(0);await page.uncheck('#autoNext');await choose('G','G05');await enterDrawing();await page.locator('#viewer').scrollIntoViewIfNeeded();
  const before=await page.evaluate(()=>current().annotations.length);await drag([200,200],[200,200]);assert.equal(await page.evaluate(()=>current().annotations.length),before);
  await drag([300,300],[301,301]);assert.match(await page.locator('#message').innerText(),/異常小/);assert.equal(await page.evaluate(()=>current().annotations.length),before+1);await page.locator('#deleteBox').click();
  const clamped=await page.evaluate(()=>{const p=new DOMPoint(-50,-50).matrixTransform(el.overlay.getScreenCTM());return imagePoint({clientX:p.x,clientY:p.y})});assert.deepEqual(clamped,{x:0,y:0});
 });
 if(process.env.MSH_TEST_SCREENSHOT){
  await page.locator('#folder').setInputFiles(root);await waitLoaded();await importPayload('backup.json',JSON.stringify(backup));await selectImage(0);await enterDrawing();await page.selectOption('#boxes',backup.images[0].annotations[0].annotationId);
 }
 const report=process.env.MSH_TEST_REPORT;if(report)await fs.writeFile(report,JSON.stringify({target,results,requests,exceptions},null,2));
 if(process.env.MSH_TEST_SCREENSHOT)await page.screenshot({path:process.env.MSH_TEST_SCREENSHOT,fullPage:true});
 console.log(JSON.stringify({passed:results.filter(r=>r.status==='PASS').length,failed:results.filter(r=>r.status==='FAIL').length}));
 if(results.some(r=>r.status==='FAIL'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
