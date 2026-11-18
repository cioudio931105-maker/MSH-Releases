"""Minimal button-to-serial adapter for the AccelStepper ConstantSpeed test."""

from __future__ import annotations

import queue
import threading
import time

import serial


COMMANDS = {"X+": b"a", "X-": b"b", "Y+": b"c", "Y-": b"d", "HOLD": b"s"}


class BasicXYLink:
    """Write only button commands; no identity query, speed policy or heartbeat.

    Opening a COM port does not verify which firmware is installed. The matching
    sketch must be uploaded separately. No movement command is retried.
    """

    def __init__(self, port: str, *, serial_factory=serial.Serial, boot_wait=2.0):
        self.port = port
        self._factory = serial_factory
        self._boot_wait = boot_wait
        self._serial = None

    def connect(self) -> None:
        if self._serial is not None:
            raise RuntimeError("連線已開啟。")
        self._serial = self._factory(self.port, 115200, write_timeout=0.2)
        # Opening an Uno serial port normally resets it; let setup() finish.
        time.sleep(self._boot_wait)

    def _write(self, command: bytes) -> None:
        if self._serial is None:
            raise RuntimeError("COM 尚未開啟。")
        if self._serial.write(command) != len(command):
            raise RuntimeError("序列寫入不完整，未重送命令。")

    def set_state(self, mode: str) -> None:
        if mode not in COMMANDS:
            raise ValueError(f"不支援的方向：{mode!r}")
        self._write(COMMANDS[mode])

    def shutdown(self) -> None:
        if self._serial is not None:
            try:
                self._write(b"q")
                self._serial.flush()
            finally:
                try:
                    self._serial.close()
                finally:
                    self._serial = None


class BasicXYSession:
    """One serial worker sends the latest button state only when it changes."""

    def __init__(self, *, link_factory=BasicXYLink):
        self.events = queue.Queue()
        self._link_factory = link_factory
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.done = threading.Event()
        self.done.set()
        self._mode = "HOLD"
        self._closing = False
        self._connected = False

    def connect(self, port: str) -> None:
        if not self.done.is_set():
            raise RuntimeError("連線工作仍在執行。")
        if not port.strip():
            raise ValueError("請先選擇 COM 連接埠。")
        with self._lock:
            self._mode = "HOLD"
            self._closing = False
            self._connected = False
        self._wake.clear()
        self.done.clear()
        worker = threading.Thread(target=self._run, args=(port,), daemon=True)
        try:
            worker.start()
        except Exception:
            self.done.set()
            raise

    def request(self, mode: str) -> None:
        if mode not in COMMANDS:
            raise ValueError(mode)
        with self._lock:
            if self._closing or not self._connected:
                return
            self._mode = mode
        self._wake.set()

    def close(self) -> None:
        with self._lock:
            self._closing = True
            self._mode = "HOLD"
        self._wake.set()

    def _run(self, port: str) -> None:
        link = None
        error = None
        try:
            link = self._link_factory(port)
            link.connect()
            with self._lock:
                self._connected = True
            self.events.put(("connected", port))
            sent = None
            while True:
                self._wake.clear()
                with self._lock:
                    closing, mode = self._closing, self._mode
                if closing:
                    break
                if mode != sent:
                    link.set_state(mode)
                    self.events.put(("state", mode))
                    sent = mode
                self._wake.wait()
        except Exception as exc:
            error = str(exc)
        finally:
            try:
                if link is not None:
                    link.shutdown()
            except Exception as exc:
                error = f"關閉線圈指令未能送出：{exc}；請手動切斷馬達電源。"
            with self._lock:
                self._connected = False
            self.events.put(("error" if error else "closed", error or "已送出關閉線圈指令。"))
            self.done.set()
