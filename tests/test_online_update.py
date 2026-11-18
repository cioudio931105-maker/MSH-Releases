"""Network, GUI and driver actions are mocked; no hardware or installer executes."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from http.client import IncompleteRead
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from msh_app.core.msh_environment import ComputeCapability, probe_compute
from msh_app.core.msh_update import (DownloadCancelled, RELEASE_REPOSITORY, UpdateCheckError, UpdateManifest,
                        _ReleaseRedirectHandler, download_installer, parse_update_manifest,
                        validate_installer_url, verify_installer)
from msh_app.core.msh_update_safety import update_blockers
from msh_app.core.msh_update_ui import UpdateController

DATA = b'MZ' + b'synthetic installer; never executed' * 50
URL = f'https://github.com/{RELEASE_REPOSITORY}/releases/download/v1.0.0/MSH_Setup_v1.0.0_ONLINE.exe'


def manifest(**kwargs):
    value = UpdateManifest('1.0.0', 'test', 'test only', URL,
                           f'https://github.com/{RELEASE_REPOSITORY}/releases/tag/v1.0.0',
                           hashlib.sha256(DATA).hexdigest(), '2026-11-17', len(DATA))
    return replace(value, **kwargs)


class Response(io.BytesIO):
    def __init__(self, data=DATA, url='https://release-assets.githubusercontent.com/test', length=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if length is None else length)}
        self.url = url

    def geturl(self):
        return self.url


class DownloadTests(unittest.TestCase):
    def download(self, path, value=None, response=None, **kwargs):
        with patch('msh_app.core.msh_update.build_opener') as factory:
            factory.return_value.open.return_value = response or Response()
            return download_installer(value or manifest(), Path(path), **kwargs)

    def test_success_exposes_only_verified_installer(self):
        with TemporaryDirectory() as directory:
            progress = Mock()
            path = self.download(directory, progress=progress)
            self.assertEqual(path.read_bytes(), DATA)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            progress.assert_called()

    def test_checksum_failure_preserves_existing_file_and_removes_partial(self):
        with TemporaryDirectory() as directory:
            existing = Path(directory) / 'old.exe'
            existing.write_bytes(b'old version')
            with self.assertRaisesRegex(UpdateCheckError, 'SHA-256'):
                self.download(directory, manifest(sha256='0' * 64))
            self.assertEqual(existing.read_bytes(), b'old version')
            self.assertEqual(list(Path(directory).iterdir()), [existing])

    def test_truncated_or_oversized_or_non_executable_response_is_rejected(self):
        for response, value in (
            (Response(DATA[:-2], length=len(DATA)), manifest()),
            (Response(DATA, length=len(DATA) - 1), manifest(size_bytes=None)),
            (Response(b'not an exe'), manifest(size_bytes=None)),
        ):
            with self.subTest(value=value), TemporaryDirectory() as directory:
                with self.assertRaises(UpdateCheckError):
                    self.download(directory, value, response)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cancellation_and_network_failure_keep_no_executable(self):
        with TemporaryDirectory() as directory:
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(DownloadCancelled):
                self.download(directory, cancel=cancel)
            cancel.clear()
            with self.assertRaises(DownloadCancelled):
                self.download(directory, cancel=cancel, progress=lambda *_: cancel.set())
            with patch('msh_app.core.msh_update.build_opener') as factory:
                factory.return_value.open.side_effect = OSError('offline')
                with self.assertRaises(UpdateCheckError):
                    download_installer(manifest(), Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_connection_break_during_stream_is_converted_to_update_error(self):
        with TemporaryDirectory() as directory, patch('msh_app.core.msh_update.build_opener') as factory:
            response = Response()
            response.read = Mock(side_effect=IncompleteRead(b'partial'))
            factory.return_value.open.return_value = response
            with self.assertRaises(UpdateCheckError):
                download_installer(manifest(), Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_disallowed_origins_and_redirects_are_blocked(self):
        for url in ('http://github.com/a.exe', 'https://example.com/a.exe',
                    'https://github.com/other/repo/releases/download/v1/a.exe', URL + '?token=secret',
                    URL.replace('/v1.0.0/', '/v1/../other/'), URL.replace('/v1.0.0/', '/%2e%2e/')):
            with self.subTest(url=url), self.assertRaises(UpdateCheckError):
                validate_installer_url(url)
        with self.assertRaises(UpdateCheckError):
            _ReleaseRedirectHandler().redirect_request(None, None, 302, '', {}, 'https://evil.example/a.exe')
        with TemporaryDirectory() as directory, self.assertRaises(UpdateCheckError):
            self.download(directory, response=Response(url='http://github.com/file.exe'))

    def test_cache_tampering_is_detected_before_execution(self):
        with TemporaryDirectory() as directory:
            path = self.download(directory)
            path.write_bytes(b'MZtampered')
            with self.assertRaises(UpdateCheckError):
                verify_installer(path, manifest().sha256)

    def test_size_schema_rejects_boolean_negative_and_huge(self):
        for size in (True, -1, 0, '123', 13 * 1024**3):
            payload = dict(schema_version=1, version='1.0.0', release_name='x', release_notes='x',
                           download_url=URL, release_page_url='https://github.com',
                           sha256='a' * 64, published_at='2026-11-17', size_bytes=size)
            with self.assertRaisesRegex(ValueError, 'size_bytes'):
                parse_update_manifest(payload)


class CapabilityTests(unittest.TestCase):
    def torch(self, cuda=True, available=True):
        module = Mock(__version__='synthetic')
        module.version.cuda = '12.4' if cuda else None
        module.cuda.is_available.return_value = available
        module.cuda.get_device_name.return_value = 'Synthetic NVIDIA GPU'
        tensor = Mock()
        tensor.__matmul__ = Mock(return_value=tensor)
        tensor.sum.return_value.item.return_value = 8.0
        module.ones.return_value = tensor
        return module

    def test_gpu_requires_real_operation_and_sync(self):
        torch = self.torch()
        self.assertEqual(probe_compute(torch).device, 'cuda:0')
        torch.ones.assert_called_once_with((2, 2), device='cuda:0')
        torch.cuda.synchronize.assert_called_once()

    def test_broken_kernel_missing_driver_and_cpu_build_use_cpu(self):
        torch = self.torch()
        torch.ones.side_effect = RuntimeError('unsupported architecture')
        self.assertEqual(probe_compute(torch).device, 'cpu')
        self.assertEqual(probe_compute(self.torch(available=False)).device, 'cpu')
        self.assertEqual(probe_compute(self.torch(cuda=False)).device, 'cpu')


class SafetyTests(unittest.TestCase):
    @patch('msh_app.core.msh_update_ui.messagebox')
    def test_manual_check_starts_download_without_an_extra_confirmation(self, boxes):
        controller = self.controller()
        controller._manual = True
        with patch.object(controller, '_offer_download') as offer:
            controller._handle('checked', manifest())
            offer.assert_called_once_with(manifest(), automatic=True)
        boxes.askyesno.assert_not_called()

    @patch('msh_app.core.msh_update_ui.messagebox')
    @patch('msh_app.core.msh_update_ui.sys.frozen', True, create=True)
    def test_explicit_update_waits_without_stopping_devices_then_closes_automatically(self, boxes):
        controller = self.controller()
        controller.gui.cap = object()
        controller.root.winfo_exists.return_value = False
        with TemporaryDirectory() as directory, patch('msh_app.core.msh_update_ui.tk.Toplevel') as window, \
                patch('msh_app.core.msh_update_ui.ttk.Label'), patch('msh_app.core.msh_update_ui.ttk.Button'):
            path = Path(directory) / 'setup.exe'
            path.write_bytes(DATA)
            controller.ready = (path, manifest())
            controller._offer_install(automatic=True)
            self.assertTrue(controller.waiting_to_install)
            controller.gui._on_close.assert_not_called()
            self.assertIsNone(controller.pending)
            controller.gui.cap = None
            controller._poll()
            controller.gui._on_close.assert_called_once()
            self.assertEqual(controller.pending, controller.ready)
            boxes.askyesno.assert_not_called()
            window.return_value.destroy.assert_called_once()

    @patch('msh_app.core.msh_update_ui.messagebox')
    def test_cancel_waiting_preserves_download_without_later_closing_the_app(self, boxes):
        controller = self.controller()
        controller.waiting_to_install = True
        controller.ready = (Path('cached.exe'), manifest())
        controller.window = Mock()
        controller.cancel_pending_install()
        controller._poll()
        self.assertIsNotNone(controller.ready)
        self.assertFalse(controller.waiting_to_install)
        controller.gui._on_close.assert_not_called()
        self.assertIsNone(controller.pending)

    def test_software_report_worker_does_not_load_gui_or_execute_a_hardware_worker(self):
        from msh_app.core.msh_workers import dispatch_worker
        with TemporaryDirectory() as directory, patch('msh_app.core.msh_environment.environment_report', return_value='software only'), \
                patch('msh_app.core.msh_workers.configure_runtime_environment'), patch('msh_app.core.msh_workers.runpy.run_path') as execute:
            output = Path(directory) / 'report.md'
            self.assertTrue(dispatch_worker(['--msh-environment-report', str(output)]))
            self.assertEqual(output.read_text(encoding='utf-8'), 'software only\n')
            execute.assert_not_called()

    def test_poll_stops_cleanly_after_normal_window_destruction(self):
        import tkinter
        controller = self.controller()
        controller.root.winfo_exists.side_effect = tkinter.TclError('application destroyed')
        controller._poll()

    def test_connected_devices_flags_threads_and_processes_block_without_actions(self):
        cases = [dict(stepper_by_axis={0: object()}), dict(cap=object()),
                 dict(_wbc_capture_running=True), dict(_work_thread=Mock(is_alive=lambda: True)),
                 dict(_stitch_process=Mock(poll=lambda: None)),
                 dict(_manual_motion_direction={0: 1})]
        for attributes in cases:
            with self.subTest(attributes=attributes):
                self.assertTrue(update_blockers(SimpleNamespace(**attributes)))
        self.assertFalse(update_blockers(SimpleNamespace(stepper_by_axis={0: None}, cap=None,
                        _work_thread=Mock(is_alive=lambda: False))))

    def controller(self):
        root = Mock()
        gui = SimpleNamespace(_on_close=Mock())
        return UpdateController(root, gui)

    @patch('msh_app.core.msh_update_ui.messagebox')
    def test_background_check_failure_is_silent_and_manual_failure_is_visible(self, boxes):
        controller = self.controller()
        controller._manual = False
        controller._handle('checked', None, OSError('offline'))
        boxes.showinfo.assert_not_called()
        controller._manual = True
        controller._handle('checked', None, OSError('offline'))
        boxes.showinfo.assert_called_once()

    @patch('msh_app.core.msh_update_ui.messagebox')
    def test_active_hardware_never_closes_for_update(self, boxes):
        controller = self.controller()
        controller.gui.cap = object()
        controller.ready = (Path('unused.exe'), manifest())
        controller._offer_install()
        controller.gui._on_close.assert_not_called()
        self.assertIsNone(controller.pending)

    @patch('msh_app.core.msh_update_ui.messagebox')
    @patch('msh_app.core.msh_update_ui.sys.frozen', True, create=True)
    def test_normal_close_failure_never_schedules_installer(self, boxes):
        controller = self.controller()
        boxes.askyesno.return_value = True
        controller.gui._on_close.side_effect = RuntimeError('cannot close')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'setup.exe'
            path.write_bytes(DATA)
            controller.ready = (path, manifest())
            controller._offer_install()
        self.assertIsNone(controller.pending)

    @patch('msh_app.core.msh_update_ui.messagebox')
    @patch('msh_app.core.msh_update_ui.sys.frozen', True, create=True)
    def test_installer_handoff_is_pending_only_after_successful_normal_close(self, boxes):
        controller = self.controller()
        boxes.askyesno.return_value = True
        controller.root.winfo_exists.return_value = False
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'setup.exe'
            path.write_bytes(DATA)
            controller.ready = (path, manifest())
            with patch('msh_app.core.msh_update_ui.subprocess.Popen') as launch:
                controller._offer_install()
                launch.assert_not_called()
                self.assertEqual(controller.pending, controller.ready)

    @patch('msh_app.core.msh_update_ui.subprocess.Popen')
    def test_helper_is_scheduled_without_shell_or_forced_termination(self, launch):
        controller = self.controller()
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'setup.exe'
            path.write_bytes(DATA)
            controller.pending = (path, manifest())
            controller.handoff_after_close()
        command = launch.call_args.args[0]
        self.assertIn('-ParentProcessId', command)
        self.assertIn('-InstallerPath', command)
        self.assertNotIn('shell', launch.call_args.kwargs)
        self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertNotIn('PSModulePath', launch.call_args.kwargs['env'])
        self.assertTrue(controller.cancel.is_set())

    @patch('msh_app.core.msh_update_ui.subprocess.Popen')
    def test_frozen_handoff_clears_child_dll_and_python_paths_then_restores_parent(self, launch):
        controller = self.controller()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'setup.exe'
            path.write_bytes(DATA)
            controller.pending = (path, manifest())
            with patch('msh_app.core.msh_update_ui.sys._MEIPASS', str(root / 'internal'), create=True), \
                    patch('msh_app.core.msh_update_ui.application_root', return_value=Path(__file__).resolve().parents[1]), \
                    patch('msh_app.core.msh_update_ui.ctypes.windll.kernel32.SetDllDirectoryW', return_value=1) as dll, \
                    patch.dict('msh_app.core.msh_update_ui.os.environ', {'PATH': str(root / 'internal') + ';C:\\Windows',
                                                           'PYTHONHOME': 'old-python', 'PYTHONPATH': 'old-source'}):
                controller.handoff_after_close()
                self.assertEqual(dll.call_args_list[0].args, (None,))
                self.assertEqual(dll.call_args_list[-1].args, (str(root / 'internal'),))
            environment = launch.call_args.kwargs['env']
            self.assertNotIn('PYTHONHOME', environment)
            self.assertNotIn('PYTHONPATH', environment)
            self.assertEqual(environment['PATH'], 'C:\\Windows')


if __name__ == '__main__':
    unittest.main()
