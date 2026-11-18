"""Physician-export training is local, preserves class IDs, and needs no old data."""
import argparse
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import yaml

from cell_stitching_project.train_user_dataset import APP_ROOT, read_user_dataset, train_user_dataset


def fixture(root):
    data=root/'physician-export';data.mkdir()
    for split in ('train','val'):
        (data/'images'/split).mkdir(parents=True)
        (data/'labels'/split).mkdir(parents=True)
        (data/'images'/split/'one.png').write_bytes(b'synthetic image bytes; validator never decodes')
        (data/'labels'/split/'one.txt').write_text('60 0.5 0.5 0.2 0.2\n',encoding='utf-8')
    names={i:f'class_{i:02d}' for i in reversed(range(61))}
    config={'path':'.','train':'images/train','val':'images/val','names':names}
    (data/'data.yaml').write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8')
    model=root/'user-model.pt';model.write_bytes(b'local synthetic checkpoint; never loaded by these tests')
    args=argparse.Namespace(data=data/'data.yaml',model=model,output=root/'training-output',name='new-run',epochs=1,imgsz=64,batch=1,device='cpu',dry_run=False)
    return data,args


class UserDatasetTrainingTests(unittest.TestCase):
    def test_relative_export_path_and_all_61_ids_are_preserved(self):
        with TemporaryDirectory() as temporary:
            data,args=fixture(Path(temporary))
            report=read_user_dataset(args.data)
            self.assertEqual(report['path'],str(data.resolve()))
            self.assertEqual(report['class_count'],61)
            self.assertEqual(report['names'][60],'class_60')
            self.assertEqual(report['splits']['train']['represented_class_ids'],[60])

    def test_dry_run_does_not_load_model_write_outputs_or_change_inputs(self):
        with TemporaryDirectory() as temporary:
            data,args=fixture(Path(temporary));args.dry_run=True
            before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob('*') if p.is_file()}
            factory=Mock()
            report=train_user_dataset(args,factory)
            factory.assert_not_called()
            self.assertTrue(report['dry_run'])
            self.assertFalse(args.output.exists())
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in data.rglob('*') if p.is_file()})

    def test_training_uses_absolute_inputs_local_initialization_and_external_outputs(self):
        with TemporaryDirectory() as temporary:
            data,args=fixture(Path(temporary))
            model=Mock(task='detect');model.train.return_value=SimpleNamespace(save_dir=args.output/args.name)
            factory=Mock(return_value=model)
            report=train_user_dataset(args,factory)
            factory.assert_called_once_with(str(args.model.resolve()))
            kwargs=model.train.call_args.kwargs
            self.assertFalse(kwargs['single_cls']);self.assertFalse(kwargs['amp']);self.assertFalse(kwargs['exist_ok'])
            self.assertEqual(kwargs['pretrained'],str(args.model.resolve()))
            descriptor=yaml.safe_load(Path(kwargs['data']).read_text(encoding='utf-8'))
            self.assertEqual(descriptor['names'],[f'class_{i:02d}' for i in range(61)])
            self.assertEqual(Path(descriptor['train']),(data/'images/train').resolve())
            self.assertEqual(Path(descriptor['val']),(data/'images/val').resolve())
            self.assertEqual(Path(report['best_model']),(args.output/args.name/'weights/best.pt').resolve())

    def test_bad_labels_remote_models_and_existing_runs_fail_before_backend(self):
        with TemporaryDirectory() as temporary:
            data,args=fixture(Path(temporary));factory=Mock()
            label=data/'labels/train/one.txt'
            for invalid in ('61 0.5 0.5 0.2 0.2','0 nan 0.5 0.2 0.2','0 0.1 0.1 0.8 0.8'):
                label.write_text(invalid,encoding='utf-8')
                with self.assertRaises(ValueError):train_user_dataset(args,factory)
            label.write_text('60 0.5 0.5 0.2 0.2',encoding='utf-8')
            original_model=args.model;args.model='https://example.invalid/model.pt'
            with self.assertRaises(FileNotFoundError):train_user_dataset(args,factory)
            args.model=original_model
            (args.output/args.name).mkdir(parents=True)
            with self.assertRaises(FileExistsError):train_user_dataset(args,factory)
            args.output=APP_ROOT/'never-create-training-output'
            with self.assertRaises(ValueError):train_user_dataset(args,factory)
            factory.assert_not_called()
            self.assertFalse((APP_ROOT/'never-create-training-output').exists())


if __name__=='__main__':unittest.main()
