"""Exercise the real Windows PowerShell helper with process launch replaced by a recorder."""
import hashlib
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
function Get-Process {
    param([int]$Id, [string]$ErrorAction)
    $fakeParent = New-Object PSObject
    $fakeParent | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {
        param([int]$Milliseconds)
        [IO.File]::WriteAllText((Join-Path $env:MSH_TEST_ROOT 'waited'), [string]$Milliseconds)
        return $env:MSH_TEST_TIMEOUT -ne '1'
    }
    return $fakeParent
}
function Start-Process {
    param([string]$FilePath, [string]$ArgumentList, [switch]$Wait, [switch]$PassThru)
    if (-not (Test-Path -LiteralPath (Join-Path $env:MSH_TEST_ROOT 'waited'))) {
        throw 'Installer was requested before waiting for the parent'
    }
    [IO.File]::WriteAllText((Join-Path $env:MSH_TEST_ROOT 'requested'), $FilePath + '|' + $ArgumentList)
    return [pscustomobject]@{ExitCode=[int]$env:MSH_TEST_INSTALL_EXIT}
}
# Error notification is intercepted; these tests must never display a dialog.
function Add-Type {
    param([string]$AssemblyName)
    [Console]::Error.WriteLine($global:Error[0].Exception.ToString())
    throw 'TEST_CAPTURED_ERROR_NO_UI'
}
& $env:MSH_TEST_HELPER -ParentProcessId 12345 -InstallerPath $env:MSH_TEST_INSTALLER -Sha256 $env:MSH_TEST_SHA
'''


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell integration')
class PowerShellHandoffTests(unittest.TestCase):
    def run_helper(self, root, *, bad_hash=False, timeout=False, install_exit=0):
        payload = root / 'never-execute.exe'
        payload.write_bytes(b'MZsynthetic fixture; process launch is mocked')
        script = root / 'harness.ps1'
        script.write_text(HARNESS, encoding='utf-8-sig')
        env = {**os.environ, 'MSH_TEST_ROOT': str(root), 'MSH_TEST_HELPER': str(ROOT / 'installer/run_update.ps1'),
               'MSH_TEST_INSTALLER': str(payload), 'MSH_TEST_SHA': '0' * 64 if bad_hash else hashlib.sha256(payload.read_bytes()).hexdigest(),
               'MSH_TEST_TIMEOUT': '1' if timeout else '0', 'MSH_TEST_INSTALL_EXIT': str(install_exit)}
        # Match the updater handoff: Windows PowerShell must initialize its own modules,
        # rather than inherit a PowerShell 7 development shell's module path.
        env.pop('PSModulePath', None)
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                               '-File', str(script)], env=env, capture_output=True, timeout=20,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def test_parent_exit_is_waited_for_then_verified_installer_is_requested(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            completed = self.run_helper(root)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((root / 'waited').read_text(), '120000')
            requested = (root / 'requested').read_text()
            self.assertIn('/NORESTART', requested)
            self.assertIn('/SILENT', requested)
            self.assertNotIn('/VERYSILENT', requested)
            self.assertIn('/MSHAUTORESTART=1', requested)

    def test_timeout_and_tampered_bytes_do_not_start_an_installer(self):
        for options in (dict(timeout=True), dict(bad_hash=True)):
            with self.subTest(options=options), TemporaryDirectory() as directory:
                root = Path(directory)
                completed = self.run_helper(root, **options)
                self.assertNotEqual(completed.returncode, 0)
                self.assertFalse((root / 'requested').exists())

    def test_failed_installer_is_reported_as_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            completed = self.run_helper(root, install_exit=1602)
            self.assertNotEqual(completed.returncode, 0)
            self.assertTrue((root / 'requested').is_file())


if __name__ == '__main__':
    unittest.main()
