"""Local detection training from physician exports, independent of old experiments."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import uuid

import yaml

from msh_app.core.msh_model_policy import local_training_options, require_local_model

APP_ROOT=Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.bmp','.tif','.tiff','.webp'}


def read_user_dataset(data_file: str | Path) -> dict:
    """Read only YAML/labels; keep the supplied names and class IDs intact."""
    data_file=Path(data_file).expanduser().resolve()
    if not data_file.is_file():raise FileNotFoundError(f'User data.yaml not found: {data_file}')
    config=yaml.safe_load(data_file.read_text(encoding='utf-8-sig'))
    if not isinstance(config,dict):raise ValueError('data.yaml must contain a dataset mapping')
    if 'download' in config:raise ValueError('Supply an extracted local dataset; MSH does not run download scripts')
    names=config.get('names')
    if isinstance(names,dict):
        if any(isinstance(k,bool) or not str(k).isdigit() for k in names):raise ValueError('Class IDs must start at zero and be contiguous')
        mapped={int(k):v for k,v in names.items()}
        if len(mapped)!=len(names) or sorted(mapped)!=list(range(len(mapped))):raise ValueError('Class IDs must start at zero and be contiguous')
        names=[mapped[i] for i in range(len(mapped))]
    if not isinstance(names,list) or not names or any(not isinstance(n,str) or not n.strip() for n in names):
        raise ValueError('Supply the original non-empty class names list or ID mapping')
    if 'nc' in config and config['nc']!=len(names):raise ValueError('nc differs from class names count')
    root_arg=config.get('path','.')
    if not isinstance(root_arg,str):raise ValueError('Dataset path must be a local directory')
    root=Path(root_arg).expanduser()
    root=(root if root.is_absolute() else data_file.parent/root).resolve()
    report={'source_yaml':str(data_file),'path':str(root),'names':names,'class_count':len(names),'splits':{}}
    for split in ('train','val'):
        entry=config.get(split)
        if not isinstance(entry,str) or '://' in entry:raise ValueError(f'{split} must name a local images directory')
        image_dir=Path(entry).expanduser()
        image_dir=(image_dir if image_dir.is_absolute() else root/image_dir).resolve()
        if not image_dir.is_dir():raise FileNotFoundError(f'{split} images not found: {image_dir}')
        if image_dir.parent.name!='images':raise ValueError(f'{split} must use images/<split> with matching labels/<split>')
        labels=image_dir.parent.parent/'labels'/image_dir.name
        images=sorted(p for p in image_dir.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)
        if not images:raise ValueError(f'No {split} images found')
        boxes=0;used=set()
        for image in images:
            label=(labels/image.relative_to(image_dir)).with_suffix('.txt')
            if not label.is_file():raise FileNotFoundError(f'Missing YOLO annotation: {label}')
            for number,line in enumerate(label.read_text(encoding='utf-8-sig').splitlines(),1):
                if not line.strip():continue
                fields=line.split()
                try:
                    if len(fields)!=5:raise ValueError('Expected class_id cx cy width height')
                    class_id=int(fields[0]);coords=[float(v) for v in fields[1:]]
                    if not 0<=class_id<len(names):raise ValueError('Class ID outside names mapping')
                    if any(not math.isfinite(v) or not 0<=v<=1 for v in coords):raise ValueError('Invalid normalized coordinates')
                    x,y,width,height=coords
                    if width<=0 or height<=0:raise ValueError('Box width/height must be positive')
                    if min(x-width/2,y-height/2)<-1e-6 or max(x+width/2,y+height/2)>1+1e-6:raise ValueError('Box outside image')
                except (ValueError,OverflowError) as exc:raise ValueError(f'{label}:{number}: {exc}') from exc
                boxes+=1;used.add(class_id)
        if not boxes:raise ValueError(f'No labelled objects in {split}')
        report[split]=str(image_dir)
        report['splits'][split]={'images':len(images),'boxes':boxes,'represented_class_ids':sorted(used)}
    if report['train']==report['val']:raise ValueError('Use separate train and val directories')
    return report


def train_user_dataset(args: argparse.Namespace, model_factory=None) -> dict:
    report=read_user_dataset(args.data)
    model_path=require_local_model(args.model)
    if Path(model_path).suffix.lower() not in {'.pt','.yaml','.yml'}:raise ValueError('Training needs a local .pt or architecture YAML; ONNX is for inference')
    output=Path(args.output).expanduser().resolve()
    if output.is_relative_to(APP_ROOT):raise ValueError('Save training results outside the MSH application project')
    if not args.name or Path(args.name).name!=args.name or args.name in {'.','..'}:raise ValueError('Run name must be a single directory name')
    run=output/args.name
    if run.exists():raise FileExistsError(f'Refusing to overwrite an existing run: {run}')
    if min(args.epochs,args.imgsz,args.batch)<=0:raise ValueError('epochs, imgsz and batch must be positive')
    report.update(model=model_path,output=str(run),single_cls=False,amp=False,dry_run=args.dry_run)
    if args.dry_run:return report
    if model_factory is None:
        from ultralytics import YOLO
        model_factory=YOLO
    model=model_factory(model_path)
    if getattr(model,'task','detect')!='detect':raise ValueError('Use a detection checkpoint for physician bounding-box data')
    # Exported path: . must resolve against the export, never the application cwd.
    descriptors=output/'dataset-descriptors';descriptors.mkdir(parents=True,exist_ok=True)
    descriptor=descriptors/(args.name+'-'+uuid.uuid4().hex+'.yaml')
    descriptor.write_text(yaml.safe_dump({k:report[k] for k in ('path','train','val','names')},allow_unicode=True,sort_keys=False),encoding='utf-8')
    result=model.train(data=str(descriptor),project=str(output),name=args.name,epochs=args.epochs,
        imgsz=args.imgsz,batch=args.batch,device=args.device,workers=0,cache=False,plots=False,
        save=True,exist_ok=False,single_cls=False,**local_training_options(model_path))
    actual=Path(getattr(result,'save_dir',run)).resolve()
    if actual!=run:raise RuntimeError(f'Trainer output differs from requested run: {actual}')
    report.update(data_descriptor=str(descriptor),best_model=str(run/'weights/best.pt'),last_model=str(run/'weights/last.pt'),
        scope='Training completion is not accuracy or hardware acceptance')
    run.mkdir(parents=True,exist_ok=True)
    (run/'msh-training-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def build_parser():
    parser=argparse.ArgumentParser(description='Train on user-supplied local YOLO/physician data; no historical model or data is supplied.')
    parser.add_argument('--data',type=Path,required=True,help='Extracted physician export data.yaml')
    parser.add_argument('--model',type=Path,required=True,help='Your local detection .pt or architecture YAML')
    parser.add_argument('--output',type=Path,required=True,help='Results directory outside this project')
    parser.add_argument('--name',default='doctor_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    parser.add_argument('--epochs',type=int,default=50)
    parser.add_argument('--imgsz',type=int,default=640)
    parser.add_argument('--batch',type=int,default=1)
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--dry-run',action='store_true',help='Validate inputs without loading a model or training')
    return parser


def main():
    print(json.dumps(train_user_dataset(build_parser().parse_args()),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
