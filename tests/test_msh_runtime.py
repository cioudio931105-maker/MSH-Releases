from __future__ import annotations

import logging
import os
import tempfile
import unittest
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest import mock

import msh_runtime


class SingleInstanceLockTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows named mutex test")
    def test_second_lock_is_rejected_until_first_lock_closes(self) -> None:
        name = rf"Local\MSH_Test_{uuid.uuid4().hex}"
        first = msh_runtime.SingleInstanceLock(name)
        second = msh_runtime.SingleInstanceLock(name)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.close()
            self.assertTrue(second.acquire())
        finally:
            first.close()
            second.close()


class RuntimeLoggingTests(unittest.TestCase):
    def test_configure_logging_writes_runtime_and_source_startup_logs(self) -> None:
        root_logger = logging.getLogger()
        original_handlers = set(root_logger.handlers)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root = Path(tmp)
                runtime_dir = root / "runtime"
                startup_log = root / "source" / "hardware_gui_startup.log"
                with mock.patch.object(msh_runtime, "local_app_data_dir", return_value=runtime_dir):
                    runtime_log = msh_runtime.configure_logging(startup_log_path=startup_log)
                marker = f"msh-runtime-test-{uuid.uuid4().hex}"
                logging.getLogger("msh.test").info(marker)
                for handler in root_logger.handlers:
                    handler.flush()

                self.assertEqual(runtime_log, runtime_dir / "msh.log")
                self.assertIn(marker, runtime_log.read_text(encoding="utf-8"))
                self.assertIn(marker, startup_log.read_text(encoding="utf-8"))
            finally:
                for handler in list(root_logger.handlers):
                    if handler not in original_handlers and isinstance(handler, RotatingFileHandler):
                        root_logger.removeHandler(handler)
                        handler.close()

    def test_diagnostics_adds_only_one_console_handler(self) -> None:
        root_logger = logging.getLogger()
        original_handlers = set(root_logger.handlers)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                runtime_dir = Path(tmp) / "runtime"
                with mock.patch.object(msh_runtime, "local_app_data_dir", return_value=runtime_dir):
                    msh_runtime.configure_logging(console=True)
                    msh_runtime.configure_logging(console=True)
                diagnostic_handlers = [
                    handler for handler in root_logger.handlers if getattr(handler, "_msh_diagnostics", False)
                ]
                self.assertEqual(len(diagnostic_handlers), 1)
            finally:
                for handler in list(root_logger.handlers):
                    if handler not in original_handlers:
                        root_logger.removeHandler(handler)
                        handler.close()


if __name__ == "__main__":
    unittest.main()
