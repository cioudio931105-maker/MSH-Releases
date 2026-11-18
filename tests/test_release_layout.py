"""Protect flattened application entrypoints and unchanged research locations."""
from pathlib import Path
import ast
import unittest
from tempfile import TemporaryDirectory
from msh_app.research_paths import original_research_root

ROOT=Path(__file__).resolve().parents[1]


class ReleaseLayoutTests(unittest.TestCase):
    def test_source_and_build_share_the_flattened_gui_location(self):
        launcher=(ROOT/'launch_msh.pyw').read_text(encoding='utf-8-sig')
        tree=ast.parse(launcher)
        assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GUI_SCRIPT' for t in n.targets))
        gui=eval(compile(ast.Expression(assignment.value),'launcher-path','eval'),{'PROJECT_ROOT':ROOT})
        self.assertEqual(gui,ROOT/'msh_app/hardware/stepper_drag_gui.py')
        self.assertTrue(gui.is_file())
        spec=(ROOT/'MSH.spec').read_text(encoding='utf-8')
        self.assertIn('ROOT / "msh_app"',spec)
        self.assertIn('"msh_app/hardware"',spec)
        self.assertIn('console=False',spec)

    def test_research_locations_survive_code_move_without_migration(self):
        expected=ROOT/'stitched_output/stitched_output/stitched_output'
        self.assertEqual(original_research_root(ROOT),expected)
        self.assertEqual(original_research_root(),expected)
        self.assertNotEqual(expected,ROOT/'msh_app')

    def test_subtype_discovery_finds_preserved_weights_after_source_move(self):
        tree=ast.parse((ROOT/'msh_app/cell_identification/object_detection.py').read_text(encoding='utf-8'))
        resolvers=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'resolve_wbc_subtype_model_path','resolve_detect_model_path'}]
        with TemporaryDirectory() as directory:
            workspace=Path(directory)
            old=original_research_root(workspace)
            model=old/'models/wbc_5cls_1000x_cls.pt'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'synthetic path-discovery fixture; never loaded')
            namespace={'Path':Path,'local_app_data_dir':lambda:workspace/'profile'}
            exec(compile(ast.Module(body=resolvers,type_ignores=[]),'model-resolvers','exec'),namespace)
            discover=namespace['resolve_wbc_subtype_model_path']
            self.assertEqual(discover(workspace/'msh_app'),str(model))
            self.assertEqual(discover(old),str(model))
            self.assertEqual(model.read_bytes(),b'synthetic path-discovery fixture; never loaded')
            detect_model=old/'models/wbc_focus_yolov8n_e_20260611.pt'
            detect_model.write_bytes(b'synthetic detector path fixture; never loaded')
            detect=namespace['resolve_detect_model_path']
            self.assertEqual(detect(workspace/'msh_app'),str(detect_model))
            self.assertEqual(detect(old),str(detect_model))

    def test_normal_shortcut_and_diagnostic_have_distinct_entrypoints(self):
        shortcut=(ROOT/'install_gui_shortcut.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('$shortcut.TargetPath = $pythonw',shortcut)
        self.assertIn('$launcher = Join-Path $projectRoot "launch_msh.pyw"',shortcut)
        self.assertNotIn('$shortcut.TargetPath = "cmd',shortcut)
        self.assertTrue((ROOT/'scripts/diagnostics/run_hardware_gui.bat').is_file())
        self.assertFalse((ROOT/'run_hardware_gui.bat').exists())


if __name__=='__main__':
    unittest.main()
