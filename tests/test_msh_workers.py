from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import msh_workers


class MshWorkerTests(unittest.TestCase):
    def test_packaged_worker_runs_inside_exe_and_never_accepts_an_arbitrary_script(self):
        with patch.object(sys,'frozen',True,create=True):
            self.assertEqual(msh_workers.worker_command('practical-stitch'),[sys.executable,'--msh-worker','practical-stitch'])
        for name in ('../../user.py','camera','serial','unknown'):
            with self.assertRaises(ValueError):
                msh_workers.worker_command(name)
            with self.assertRaises(ValueError):
                msh_workers.dispatch_worker(['--msh-worker',name])

    def test_dispatch_preserves_arguments_and_does_not_enter_gui_path(self):
        before=list(sys.argv)
        paths=list(sys.path)
        seen=[]
        with patch.object(msh_workers,'configure_logging'),patch.object(msh_workers,'configure_runtime_environment'),patch.object(msh_workers.runpy,'run_path',side_effect=lambda script,run_name:seen.append((script,run_name,list(sys.argv)))):
            self.assertTrue(msh_workers.dispatch_worker(['--msh-worker','practical-stitch','--help']))
        self.assertEqual(seen[0][1],'__main__')
        self.assertEqual(seen[0][2][-1],'--help')
        self.assertTrue(Path(seen[0][0]).is_file())
        self.assertEqual(sys.argv,before)
        self.assertEqual(sys.path,paths)
        self.assertFalse(msh_workers.dispatch_worker(['--diagnostics']))
