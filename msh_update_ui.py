"""Main-thread Tk UI for background checks and verified update downloads."""
from __future__ import annotations

import logging
import ctypes
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from msh_environment import (BASLER_DOWNLOAD_URL, NVIDIA_DRIVER_URL,
                             compute_capability, environment_report)
from msh_runtime import application_root, local_app_data_dir
from msh_update import (DownloadCancelled, UpdateManifest, check_for_update,
                        download_installer, verify_installer)
from msh_update_safety import update_blockers
from msh_version import __version__


class UpdateController:
    def __init__(self, root: tk.Tk, gui: object) -> None:
        self.root = root
        self.gui = gui
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.checking = False
        self.downloading = False
        self.auto_update_requested = False
        self.waiting_to_install = False
        self.pending: tuple[Path, UpdateManifest] | None = None
        self.ready: tuple[Path, UpdateManifest] | None = None
        self.deferred_manifest: UpdateManifest | None = None
        self.window = None
        self.progress = None
        self.status = None
        self.logger = logging.getLogger("msh.update")
        self.root.after(150, self._poll)

    def _poll(self) -> None:
        # Workers never call Tk, including root.after, from a foreign thread.
        for _ in range(50):
            try:
                event, values = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle(event, *values)
        if self.deferred_manifest is not None and not update_blockers(self.gui):
            manifest = self.deferred_manifest
            self.deferred_manifest = None
            self._offer_download(manifest)
        if self.waiting_to_install and not update_blockers(self.gui):
            self.waiting_to_install = False
            self._offer_install(automatic=True)
        try:
            if self.root.winfo_exists():
                self.root.after(150, self._poll)
        except tk.TclError:
            return

    def _background(self, event: str, operation) -> None:
        def run() -> None:
            try:
                result = operation()
                self.events.put((event, (result, None)))
            except Exception as exc:
                self.events.put((event, (None, exc)))
        threading.Thread(target=run, name=f"msh-{event}", daemon=True).start()

    def check(self, manual: bool = True) -> None:
        if self.checking or self.downloading:
            if manual:
                messagebox.showinfo("MSH 更新", "正在檢查或下載更新，請稍候。", parent=self.root)
            return
        if self.ready is not None:
            if manual:
                self.auto_update_requested = True
                self._offer_install(automatic=True)
            return
        self.checking = True
        self._manual = manual
        self.auto_update_requested = manual
        self._background("checked", lambda: check_for_update(__version__))

    def _handle(self, event: str, result, error=None) -> None:
        if event == "checked":
            self.checking = False
            if error is not None:
                self.logger.warning("Update check unavailable: %s", error)
                if self._manual:
                    messagebox.showinfo("MSH 檢查更新", "目前無法取得更新資訊。請確認網路及發行檔案的存取權限。\n"
                                        "您可以照常使用目前版本，稍後再檢查。", parent=self.root)
            elif result is None:
                if self._manual:
                    messagebox.showinfo("MSH 檢查更新", f"目前已是最新版本：v{__version__}", parent=self.root)
            else:
                self._offer_download(result, automatic=self._manual)
        elif event == "progress":
            if self.window is not None:
                count, total = result
                if total:
                    self.progress.configure(mode="determinate", maximum=total, value=count)
                self.status.set(f"已下載 {count / 1024**2:.1f} MB" +
                                (f" / {total / 1024**2:.1f} MB" if total else ""))
        elif event == "downloaded":
            self.downloading = False
            if self.window is not None:
                self.window.destroy()
                self.window = None
            if error is not None:
                if not isinstance(error, DownloadCancelled):
                    self.logger.warning("Update download failed: %s", error)
                    messagebox.showwarning("MSH 更新", str(error), parent=self.root)
            else:
                self.ready = (result, self._manifest)
                self._offer_install(automatic=self.auto_update_requested)
        elif event == "diagnosed":
            self.diagnosing = False
            messagebox.showinfo("MSH 環境診斷", str(error) if error else result, parent=self.root)
        elif event == "startup-compute":
            if error is not None:
                self.logger.warning("Compute probe failed: %s", error)
            elif result.device != "cuda:0":
                self._idle_notice(result.reason + "\nCPU 模式的即時掃描速度仍需驗證。")

    def _idle_notice(self, text: str) -> None:
        if update_blockers(self.gui):
            self.root.after(5000, lambda: self._idle_notice(text))
        else:
            messagebox.showinfo("MSH 運算模式", text, parent=self.root)

    def _offer_download(self, manifest: UpdateManifest, automatic: bool = False) -> None:
        if self.downloading or self.ready is not None:
            return
        if not automatic and update_blockers(self.gui):
            # Do not interrupt device work with a modal dialog.
            self.deferred_manifest = manifest
            return
        if not automatic and not messagebox.askyesno("MSH 有可用更新",
                f"目前 v{__version__} → 新版 v{manifest.version}\n\n{manifest.release_notes}\n\n"
                "是否開始自動更新？下載後會在工作結束、設備斷線時正常關閉並安裝新版。", parent=self.root):
            return
        self.auto_update_requested = True
        self._manifest = manifest
        self.downloading = True
        self.cancel.clear()
        self.window = tk.Toplevel(self.root)
        self.window.title("MSH 下載更新")
        self.window.transient(self.root)
        self.status = tk.StringVar(value="準備下載…")
        ttk.Label(self.window, textvariable=self.status, padding=12).pack()
        self.progress = ttk.Progressbar(self.window, length=350, mode="determinate")
        self.progress.pack(padx=12, pady=6)
        ttk.Button(self.window, text="取消下載", command=self.cancel.set).pack(pady=12)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel.set)
        self._background("downloaded", lambda: download_installer(
            manifest, local_app_data_dir() / "updates", cancel=self.cancel,
            progress=lambda count, total: self.events.put(("progress", ((count, total),))),
        ))

    def cancel_pending_install(self) -> None:
        self.waiting_to_install = False
        self.auto_update_requested = False
        if self.window is not None:
            self.window.destroy()
            self.window = None

    def _offer_install(self, automatic: bool = False) -> None:
        if self.ready is None:
            return
        blockers = update_blockers(self.gui)
        if blockers:
            if automatic:
                self.waiting_to_install = True
                if self.window is None:
                    self.window = tk.Toplevel(self.root)
                    self.window.title("MSH 等待安全更新")
                    self.window.transient(self.root)
                    ttk.Label(self.window, text="新版已下載。請正常結束工作並斷開設備：\n" +
                              "\n".join(blockers) + "\n完成後會自動安裝；不會替您停止設備。", padding=12).pack()
                    ttk.Button(self.window, text="稍後再更新", command=self.cancel_pending_install).pack(pady=12)
                    self.window.protocol("WM_DELETE_WINDOW", self.cancel_pending_install)
                return
            messagebox.showinfo("MSH 更新已下載", "\n".join(blockers) +
                "\n完成後，按「說明 → 檢查更新」繼續安裝。\n程式不會替您強制停止設備。", parent=self.root)
            return
        self.waiting_to_install = False
        if self.window is not None:
            self.window.destroy()
            self.window = None
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("MSH 更新已下載", "目前為原始碼模式。安裝檔只更新已安裝的 APP，不會更新 Git 原始碼。\n"
                                f"已驗證的安裝檔：\n{self.ready[0]}", parent=self.root)
            return
        if not automatic and not messagebox.askyesno("MSH 安裝更新", "新版已下載並通過 SHA-256 驗證。\n"
                "是否正常關閉 MSH 並啟動安裝程式？", parent=self.root):
            return
        # Recheck after the modal dialog; background work may have changed.
        if update_blockers(self.gui):
            messagebox.showwarning("MSH 更新", "工作狀態已改變，請先結束工作再安裝。", parent=self.root)
            return
        try:
            verify_installer(self.ready[0], self.ready[1].sha256, self.ready[1].size_bytes)
            self.gui._on_close()
        except Exception as exc:
            self.logger.exception("Normal close for update failed")
            messagebox.showerror("MSH 更新", f"未啟動安裝：{exc}", parent=self.root)
            return
        try:
            closed = not self.root.winfo_exists()
        except tk.TclError:
            closed = True
        if closed:
            self.pending = self.ready

    def diagnose(self) -> None:
        if getattr(self, "diagnosing", False):
            return
        self.diagnosing = True
        self._background("diagnosed", environment_report)

    def startup_probe(self) -> None:
        if update_blockers(self.gui):
            self.root.after(5000, self.startup_probe)
            return
        self._background("startup-compute", compute_capability)

    def handoff_after_close(self) -> None:
        self.cancel.set()
        if self.pending is None:
            return
        installer, manifest = self.pending
        helper = application_root() / "installer" / "run_update.ps1"
        verify_installer(installer, manifest.sha256, manifest.size_bytes)
        if os.name != "nt" or not helper.is_file():
            raise RuntimeError("更新安裝輔助程式不存在或非 Windows 系統。")
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        environment = dict(os.environ)
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for name in ("PSModulePath", "PYTHONHOME", "PYTHONPATH"):
            environment.pop(name, None)
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            base = os.path.normcase(os.path.abspath(frozen_root))
            environment["PATH"] = os.pathsep.join(
                part for part in environment.get("PATH", "").split(os.pathsep)
                if part and not (os.path.normcase(os.path.abspath(part)) == base
                                 or os.path.normcase(os.path.abspath(part)).startswith(base + os.sep)))
            # PyInstaller's Windows DLL search path is inherited by child processes.
            set_dll_directory = ctypes.windll.kernel32.SetDllDirectoryW
            set_dll_directory.argtypes = (ctypes.c_wchar_p,)
            set_dll_directory.restype = ctypes.c_int
            if not set_dll_directory(None):
                raise OSError("Cannot restore the system DLL search path for Setup")
        try:
            subprocess.Popen([
                str(powershell), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass", "-File", str(helper),
                "-ParentProcessId", str(os.getpid()), "-InstallerPath", str(installer),
                "-Sha256", manifest.sha256,
            ], creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
                env=environment, cwd=str(installer.parent))
        finally:
            if frozen_root:
                set_dll_directory(str(frozen_root))


def install_help_menu(root: tk.Tk, gui: object) -> UpdateController:
    controller = UpdateController(root, gui)
    menu = tk.Menu(root)
    help_menu = tk.Menu(menu, tearoff=False)
    help_menu.add_command(label="檢查更新…", command=controller.check)
    help_menu.add_command(label="環境診斷…", command=controller.diagnose)
    help_menu.add_command(label="NVIDIA 官方驅動下載", command=lambda: webbrowser.open(NVIDIA_DRIVER_URL))
    help_menu.add_command(label="Basler 官方元件下載", command=lambda: webbrowser.open(BASLER_DOWNLOAD_URL))
    help_menu.add_separator()
    help_menu.add_command(label="關於 MSH", command=lambda: messagebox.showinfo(
        "關於 MSH", f"Microscope Scanner Helper\n版本 v{__version__}", parent=root))
    menu.add_cascade(label="說明", menu=help_menu)
    root.configure(menu=menu)
    root.after(3000, lambda: controller.check(manual=False))
    root.after(500, controller.startup_probe)
    return controller
