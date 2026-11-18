from pathlib import Path
from collections import defaultdict
import hashlib
import json
import os
import stat
import subprocess
import time
from datetime import datetime, timezone



def scan_workspace(root,output):
    from tools.release_audit.explanations import add_explanations, file_role
    ROOT=Path(root).resolve()
    OUT=Path(output).resolve()
    if OUT == ROOT or any(p in {'.git','.codex','.aws'} for p in OUT.parts):raise ValueError('Unsafe output directory')
    OUT.mkdir(parents=True,exist_ok=True)
    marker=OUT/'.msh-artifact-review'
    if any(OUT.iterdir()) and not marker.exists():raise ValueError('Output is not an existing artifact review directory')
    marker.touch()
    tracked=set(subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT,capture_output=True).stdout.decode().strip('\0').split('\0'))
    worktrees=[]
    for line in subprocess.run(['git','worktree','list','--porcelain'],cwd=ROOT,capture_output=True).stdout.decode().splitlines():
        if line.startswith('worktree '):
            p=Path(line[9:]).resolve()
            if p!=ROOT and p.is_relative_to(ROOT):worktrees.append(p)
    totals=defaultdict(lambda:{'bytes':0,'files':0})
    groups=defaultdict(lambda:{'bytes':0,'files':0,'models':0,'images':0,'labels':0})
    models=[];errors=[];skipped=[];started=time.monotonic()
    weights={'.pt','.pth','.ckpt','.onnx','.engine','.safetensors','.weights','.omc','.caffemodel'}
    images={'.jpg','.jpeg','.png','.bmp','.tif','.tiff','.webp','.dcm','.svs'}
    def group_for(parts):
        top=parts[0]
        if top.startswith(('.venv','.conda')):return top,'environment'
        if top in ('build','dist'):return '/'.join(parts[:min(2,len(parts)-1)]) or top,'build'
        if top=='tmp':
            name='/'.join(parts[:min(2,len(parts)-1)])
            return name,'research-demo' if 'training_recording' in name else 'local-evidence'
        if len(parts)==1:return parts[0],'model' if Path(parts[0]).suffix.lower() in weights else 'root-file'
        if top=='stitched_output':
            i=0
            while i<len(parts) and parts[i]=='stitched_output':i+=1
            markers={'captured','captured_steps','runs','data','dataset','datasets','models','output','outputs','experiments'}
            if i<len(parts) and parts[i] in markers:
                count=i+2 if parts[i] in {'captured','captured_steps','runs','experiments'} and len(parts)>i+2 else i+1
                return '/'.join(parts[:count]),'research'
            return '/'.join(parts[:min(i+1,len(parts)-1)]),'mixed-legacy'
        if top in {'data','datasets','dataset','models','reports','runs','output','session_output'}:
            return '/'.join(parts[:min(2,len(parts)-1)]),'research'
        return top,'application-and-local'

    with (OUT/'files.jsonl').open('w',encoding='utf-8') as inventory:
        for top in sorted(ROOT.iterdir(),key=lambda p:p.name.casefold()):
            if top.name in {'.git','.agents','.codex','.aws'}:skipped.append(top.name);continue
            stack=[top]
            while stack:
                p=stack.pop()
                if p==OUT or p in worktrees:skipped.append(p.relative_to(ROOT).as_posix());continue
                try:
                    info=p.lstat()
                    if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        skipped.append(p.relative_to(ROOT).as_posix());continue
                    if stat.S_ISDIR(info.st_mode):
                        if p.name=='.git':skipped.append(p.relative_to(ROOT).as_posix());continue
                        with os.scandir(p) as entries:stack.extend(Path(e.path) for e in entries)
                        continue
                    if not stat.S_ISREG(info.st_mode):continue
                    rel=p.relative_to(ROOT).as_posix();parts=rel.split('/')
                    group,category=group_for(parts)
                    g=groups[group];g['bytes']+=info.st_size;g['files']+=1;g['category']=category
                    if len(g.setdefault('samples',[]))<4:g['samples'].append(rel)
                    suffixes=g.setdefault('suffix_counts',{})
                    suffixes[p.suffix.lower() or '(no extension)']=suffixes.get(p.suffix.lower() or '(no extension)',0)+1
                    if rel in tracked:g['tracked']=g.get('tracked',0)+1
                    suffix=p.suffix.lower()
                    if suffix in images:g['images']+=1
                    if suffix in {'.txt','.xml','.json'} and any(s in {'labels','annotations'} for s in parts):g['labels']+=1
                    if suffix in weights and category!='environment':
                        g['models']+=1
                        model={'path':rel,'bytes':info.st_size,'group':group,'category':category}
                        if category not in {'build','local-evidence'}:
                            with p.open('rb') as f:model['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
                        models.append(model)
                    totals[top.name]['bytes']+=info.st_size;totals[top.name]['files']+=1
                    inventory.write(json.dumps({'path':rel,'bytes':info.st_size,'group':group,'category':category,'tracked':rel in tracked,'role':file_role(rel)},ensure_ascii=False)+'\n')
                except (OSError,ValueError) as exc:errors.append({'path':str(p.relative_to(ROOT)),'type':type(exc).__name__})
            print(top.name,totals[top.name]['files'],round(totals[top.name]['bytes']/1024**3,3),'GiB',flush=True)
    digests=defaultdict(list)
    for model in models:
        if model.get('sha256'):digests[model['sha256']].append(model['path'])
    duplicates=[{'sha256':h,'paths':p} for h,p in digests.items() if len(p)>1]
    report={'root':str(ROOT),'created':datetime.now(timezone.utc).isoformat(),'total_bytes':sum(v['bytes'] for v in totals.values()),'total_files':sum(v['files'] for v in totals.values()),'root_totals':dict(totals),'groups':[dict(path=k,**v) for k,v in groups.items()],'models':models,'verified_model_duplicates':duplicates,'skipped':skipped,'errors':errors,'seconds':round(time.monotonic()-started,2),'source_files':sum(1 for p in tracked if p and (ROOT/p).is_file()),'data_moved':False,'data_deleted':False,'scope':'local metadata only; no model loading or hardware access'}
    add_explanations(report)
    (OUT/'inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('TOTAL',report['total_files'],round(report['total_bytes']/1024**3,2),'GiB','models',len(models),'verified duplicate groups',len(duplicates),'errors',len(errors),flush=True)

    return report


def main():
    import argparse
    import sys
    base=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(base))
    from tools.release_audit.catalog import write_catalog
    parser=argparse.ArgumentParser(description='Read-only local artifact inventory and review browser; never deletes or moves research files.')
    parser.add_argument('--root',type=Path,default=base)
    parser.add_argument('--output',type=Path,default=base/'tmp/release-artifact-review')
    args=parser.parse_args()
    report=scan_workspace(args.root,args.output)
    print(write_catalog(report,args.output.resolve()))

if __name__=='__main__':
    main()
