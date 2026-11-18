"""Deletion guidance must distinguish active runtime, data, and old copies."""
from pathlib import Path
import json
import unittest
from tools.release_audit.explanations import add_explanations, explain_file, file_role, group_explanation


class ArtifactExplanationTests(unittest.TestCase):
    def test_active_environment_is_required_but_unknown_paths_never_assume_safe(self):
        active=group_explanation('.venv312')
        self.assertEqual(active['risk'],'required')
        self.assertIn('無法開啟',active['deletion_effect'])
        self.assertIn('pythonw.exe',active['source_gui'])
        unknown=group_explanation('tmp/new_unreviewed_experiment')
        self.assertEqual(unknown['risk'],'unknown')
        self.assertIn('無法排除',unknown['deletion_effect'])

    def test_mixed_hardware_and_backup_are_not_treated_as_cache(self):
        old='stitched_output/stitched_output/stitched_output/hardware'
        group=group_explanation(old)
        self.assertEqual(group['risk'],'research')
        _,profile=explain_file(old+'/camera_profiles/camera.pfs',old)
        _,cache=explain_file(old+'/__pycache__/driver.pyc',old)
        self.assertEqual(profile['risk'],'research')
        self.assertEqual(cache['risk'],'cache')
        backup=group_explanation('tmp/usb_latest_20261019')
        self.assertEqual(backup['risk'],'research')
        self.assertIn('Git',backup['purpose'])
        self.assertIn('尚未重新驗證',backup['certainty'])

    def test_ocr_training_and_synthetic_checkpoints_have_different_meanings(self):
        ocr='dist/MSH/_internal/pypylon/pylonDataProcessingPlugins/PylonVToolPackageA/ocr/Document_Rej.omc'
        best='tmp/msh_training_recording_demo_20261021/runs61/example/weights/best.pt'
        synthetic='tmp/msh014-model-validation/train-smoke/weights/best.pt'
        self.assertEqual(file_role(ocr),'ocr')
        self.assertEqual(file_role(best),'best61')
        self.assertEqual(file_role(synthetic),'synthetic-model')
        report={'groups':[],'models':[{'path':ocr},{'path':best},{'path':synthetic}]}
        add_explanations(report)
        self.assertEqual(report['model_types'],{'third_party_ocr':1,'pytorch_checkpoints':2})
        self.assertIn('不是你的白血球',report['explanations']['roles']['ocr']['purpose'])
        self.assertIn('不一定相同',report['explanations']['roles']['last']['purpose'])

    def test_training_inputs_do_not_equate_to_gui_code_or_disposable_outputs(self):
        parent,raw=explain_file('data/training/doctor_blood_smear_20260821/01_raw_blood_smear_images_to_annotate/one.png','data/training')
        self.assertEqual(raw['risk'],'research')
        self.assertIn('原始顯微鏡',raw['purpose'])
        self.assertIn('既有已訓練模型',parent['deletion_effect'])
        newest=group_explanation('tmp/r1109c')
        self.assertEqual(newest['risk'],'required')
        self.assertIn('連結將失效',newest['deletion_effect'])

    def test_all_explanations_have_separate_impacts_and_evidence_limits(self):
        report={'groups':[],'models':[]}
        add_explanations(report)
        fields=('title','purpose','source_gui','installed_gui','features','deletion_effect','action','certainty','risk')
        for kind in ('groups','roles'):
            for key,spec in report['explanations'][kind].items():
                for field in fields:
                    with self.subTest(kind=kind,key=key,field=field):
                        self.assertTrue(spec[field])
        self.assertIn('未逐項刪除實驗',report['explanation_scope'])


if __name__=='__main__':
    unittest.main()
