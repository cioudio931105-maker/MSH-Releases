"""Temporary standalone four-button GUI; no camera or legacy motion imports."""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import ttk

from serial.tools import list_ports

from msh_app.hardware.basic_xy import BasicXYSession


class BasicMotorGUI:
    def __init__(self, root: tk.Tk, *, session=None, port_provider=list_ports.comports):
        self.root = root
        self.session = session if session is not None else BasicXYSession()
        self._port_provider = port_provider
        self._closing = False
        self._pressed = None
        self._connected = False
        self._step_pending = False
        self._step_latched = False
        self._active_step_count = 5
        root.title("MSH ConstantSpeed 雙馬達測試（單 UNO）")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=16)
        frame.grid(sticky="nsew")
        self.port_var = tk.StringVar()
        self.status_var = tk.StringVar(value="未連線。微調需先燒錄新版配套韌體，再選擇 UNO 的 COM。")
        self.motion_mode = tk.StringVar(value="step")
        self.step_count_var = tk.StringVar(value="5")
        ttk.Label(frame, text="UNO COM 連接埠").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(frame, textvariable=self.port_var, state="readonly", width=13)
        self.port_combo.grid(row=0, column=1, padx=6)
        self.refresh_button = ttk.Button(frame, text="重新整理", command=self._refresh)
        self.refresh_button.grid(row=0, column=2, padx=4)
        self.connect_button = ttk.Button(frame, text="連線", command=self._connect)
        self.connect_button.grid(row=0, column=3, padx=4)
        modes = ttk.Frame(frame)
        modes.grid(row=1, column=0, columnspan=4, sticky="w", pady=(12, 0))
        self.mode_buttons = [
            ttk.Radiobutton(modes, text=label, variable=self.motion_mode, value=value,
                            command=self._change_mode)
            for label, value in (("微調：每次", "step"), ("連續：按住移動", "continuous"))
        ]
        for column, button in enumerate(self.mode_buttons):
            button.grid(row=0, column=column * 3, padx=(0, 8))
        self.step_count_combo = ttk.Combobox(modes, textvariable=self.step_count_var,
                                            values=("5", "10"), state="readonly", width=3)
        self.step_count_combo.grid(row=0, column=1)
        ttk.Label(modes, text="整步").grid(row=0, column=2, padx=(4, 16))
        ttk.Label(frame, text="微調：點一下移動選定步數，不連發，完成後才接受下一次。\n連續：50 整步／秒，放開停止；關閉視窗時關閉線圈。", justify="left").grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(10, 8)
        )
        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, columnspan=4, sticky="w")
        self.motion_buttons = {}
        for column, (label, mode) in enumerate((
            ("X 前進", "X+"), ("X 後退", "X-"), ("Y 前進", "Y+"), ("Y 後退", "Y-"),
        )):
            button = ttk.Button(controls, text=label, state="disabled", width=12)
            button.grid(row=0, column=column, padx=(0, 6))
            button.bind("<ButtonPress-1>", lambda _e, m=mode: self._press(m))
            button.bind("<Leave>", lambda _e, m=mode: self._leave(m))
            self.motion_buttons[mode] = button
        ttk.Label(frame, textvariable=self.status_var, wraplength=525, justify="left").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(12, 0)
        )
        root.bind("<ButtonRelease-1>", lambda _e: self._release(), add="+")
        root.bind("<FocusOut>", self._focus_out, add="+")
        root.bind("<Unmap>", lambda _e: self._stop(), add="+")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._refresh()
        self._tick_id = root.after(50, self._tick)

    def _refresh(self):
        try:
            ports = sorted({p.device for p in self._port_provider()})
            self.port_combo["values"] = ports
            # Selecting a COM port is an explicit user action, never guessed.
            if self.port_var.get() not in ports:
                self.port_var.set("")
        except Exception as exc:
            self.status_var.set(f"無法列出 COM：{exc}")

    def _connection_controls(self, enabled):
        self.port_combo.configure(state="readonly" if enabled else "disabled")
        self.refresh_button.configure(state="normal" if enabled else "disabled")
        self.connect_button.configure(state="normal" if enabled else "disabled")

    def _motion_controls(self, enabled):
        for button in self.motion_buttons.values():
            button.configure(state="normal" if enabled and not self._step_pending else "disabled")
        self.step_count_combo.configure(state="readonly" if not self._step_pending and not self._closing else "disabled")

    def _change_mode(self):
        self._stop()

    def _release(self):
        self._step_latched = False
        if self.motion_mode.get() == "continuous":
            self._stop()

    def _connect(self):
        try:
            self.session.connect(self.port_var.get())
        except Exception as exc:
            self.status_var.set(str(exc))
            return
        self._connection_controls(False)
        self.status_var.set("正在開啟 COM，等待 UNO 啟動…")

    def _press(self, mode):
        if self._connected and not self._closing and not self._step_pending:
            if self.motion_mode.get() == "step":
                if self._step_latched or self._step_pending:
                    return
                self._step_latched = True
                count = int(self.step_count_var.get())
                if self.session.request_step(mode, count):
                    self._active_step_count = count
                    self._step_pending = True
                    self._motion_controls(False)
                    self.status_var.set(f"正在要求 {count} 整步微調，等待韌體完成…")
                return
            self._pressed = mode
            self.session.request(mode)

    def _leave(self, mode):
        if self._pressed == mode:
            self._stop()

    def _stop(self):
        self._pressed = None
        self._step_latched = False
        self.session.request("HOLD")

    def _focus_out(self, _event):
        # Focus also moves between widgets inside this window. Wait until that
        # transfer finishes; only leaving this application stops motion.
        self.root.after_idle(self._stop_if_unfocused)

    def _stop_if_unfocused(self):
        focused = self.root.focus_displayof()
        if focused is None or focused.winfo_toplevel() != self.root:
            self._stop()

    def close(self):
        if self._closing:
            return
        self._closing = True
        self._pressed = None
        self._motion_controls(False)
        self._connection_controls(False)
        for button in self.mode_buttons:
            button.configure(state="disabled")
        self.status_var.set("正在停止兩軸並關閉線圈輸出…")
        self.session.close()

    def _tick(self):
        while True:
            try:
                kind, value = self.session.events.get_nowait()
            except queue.Empty:
                break
            if kind == "connected":
                self._connected = True
                if not self._closing:
                    self._motion_controls(True)
                    self.status_var.set(f"已開啟 {value}。請確認已上傳含微調的新版配套韌體。")
            elif kind == "state" and not self._closing:
                self.status_var.set("已送出停止指令，保持目前線圈狀態。" if value == "HOLD" else f"已送出 {value[0]} {'前進' if value[1] == '+' else '後退'}指令。")
            elif kind == "step_sent" and not self._closing:
                self.status_var.set(f"已送出 {self._active_step_count} 整步微調，等待韌體回報完成…")
            elif kind in ("step_done", "step_cancelled"):
                self._step_pending = False
                if not self._closing:
                    self._motion_controls(self._connected)
                    self.status_var.set(
                        f"韌體回報 {value[0]} {'前進' if value[1] == '+' else '後退'} {self._active_step_count} 整步完成。"
                        if kind == "step_done" else "微調已取消，請確認畫面後再操作。"
                    )
            elif kind in ("error", "closed"):
                self._connected = False
                self._pressed = None
                self._step_pending = False
                self._step_latched = False
                self._motion_controls(False)
                if not self._closing:
                    self._connection_controls(True)
                self.status_var.set(str(value))
        if self._closing and self.session.done.is_set():
            self.root.destroy()
            return
        self._tick_id = self.root.after(50, self._tick)


def main():
    root = tk.Tk()
    BasicMotorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
