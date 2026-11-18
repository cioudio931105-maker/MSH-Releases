"""Verify the cleanup review never modifies source data or guesses duplicates."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from tools.release_audit.inventory import scan_workspace
from tools.release_audit.catalog import write_catalog


class ArtifactInventoryTests(unittest.TestCase):
    def test_inventory_preserves_inputs_and_only_confirms_equal_model_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            root=base/'project'
            root.mkdir()
            (root/'models').mkdir()
            (root/'data/training').mkdir(parents=True)
            (root/'models/a.pt').write_bytes(b'checkpoint A')
            (root/'models/b.pt').write_bytes(b'checkpoint A')
            (root/'models/c.pt').write_bytes(b'checkpoint B')
            (root/'data/training/sample.png').write_bytes(b'synthetic image fixture')
            (root/'data/training/labels.txt').write_text('synthetic label',encoding='utf-8')
            (root/'.git').mkdir()
            (root/'.git/do-not-read.pt').write_bytes(b'git internals excluded')
            before={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            report=scan_workspace(root,base/'review')
            after={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            self.assertEqual(report['total_files'],5)
            self.assertEqual(len(report['models']),3)
            self.assertEqual(len(report['verified_model_duplicates']),1)
            self.assertEqual(set(report['verified_model_duplicates'][0]['paths']),{'models/a.pt','models/b.pt'})
            self.assertFalse(report['data_moved'])
            self.assertFalse(report['data_deleted'])
            self.assertEqual(report['errors'],[])
            html=write_catalog(report,base/'review')
            content=html.read_text(encoding='utf-8')
            self.assertIn('delete_authorized:false',content)
            self.assertNotIn('/*__INVENTORY__*/null',content)
            self.assertIn('connect-src \'none\'',content)

    def test_review_refuses_project_root_or_non_review_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(ValueError,'Unsafe output'):
                scan_workspace(root,root)
            out=root/'user-data'
            out.mkdir()
            sentinel=out/'inventory.json'
            sentinel.write_text('user owned original',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'not an existing artifact'):
                scan_workspace(root,out)
            self.assertEqual(sentinel.read_text(encoding='utf-8'),'user owned original')


if __name__=='__main__':
    unittest.main()
