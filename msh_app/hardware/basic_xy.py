"""Minimal button-to-serial adapter for the AccelStepper ConstantSpeed test."""

from __future__ import annotations

import queue
import threading
import time

import serial


COMMANDS = {"X+": b"a", "X-": b"b", "Y+": b"c", "Y-": b"d", "HOLD": b"s"}
STEP_COMMANDS = {"X+": b"A", "X-": b"B", "Y+": b"C", "Y-": b"D"}
STEP_COMMANDS_BY_COUNT = {
    1: STEP_COMMANDS,
    5: {"X+": b"E", "X-": b"F", "Y+": b"G", "Y-": b"H"},
    10: {"X+": b"I", "X-": b"J", "Y+": b"K", "Y-": b"L"},
}


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
        self._reply = b""

    def connect(self) -> None:
        if self._serial is not None:
            raise RuntimeError("連線已開啟。")
        self._serial = self._factory(self.port, 115200, timeout=0, write_timeout=0.2)
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

    def step_once(self, mode: str, steps: int = 1) -> None:
        if type(steps) is not int or steps not in STEP_COMMANDS_BY_COUNT or mode not in STEP_COMMANDS:
            raise ValueError((mode, steps))
        if self._serial is None:
            raise RuntimeError("COM 尚未開啟。")
        self._reply = b""
        self._serial.reset_input_buffer()
        self._write(STEP_COMMANDS_BY_COUNT[steps][mode])

    def poll_step_result(self):
        self._reply += self._serial.read(64)
        while b"\n" in self._reply:
            line, self._reply = self._reply.split(b"\n", 1)
            if line.strip() == b"STEP DONE":
                return "done"
            if line.strip() == b"STEP CANCELLED":
                return "cancelled"
        if len(self._reply) > 256:
            raise RuntimeError("微調回覆格式錯誤；未重送移動。")
        return None

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
        self._pending_step = None
        self._pending_step_count = 1
        self._cancel_step = False

    def connect(self, port: str) -> None:
        if not self.done.is_set():
            raise RuntimeError("連線工作仍在執行。")
        if not port.strip():
            raise ValueError("請先選擇 COM 連接埠。")
        with self._lock:
            self._mode = "HOLD"
            self._closing = False
            self._connected = False
            self._pending_step = None
            self._pending_step_count = 1
            self._cancel_step = False
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
            if self._pending_step is not None:
                self._cancel_step = True
        self._wake.set()

    def request_step(self, mode: str, steps: int = 1) -> bool:
        if type(steps) is not int or steps not in STEP_COMMANDS_BY_COUNT or mode not in STEP_COMMANDS:
            raise ValueError((mode, steps))
        with self._lock:
            if self._closing or not self._connected or self._pending_step is not None:
                return False
            self._mode = "HOLD"
            self._pending_step = mode
            self._pending_step_count = steps
            self._cancel_step = False
        self._wake.set()
        return True

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
            step_sent = False
            cancel_sent = False
            step_deadline = None
            while True:
                self._wake.clear()
                with self._lock:
                    closing, mode = self._closing, self._mode
                    step, cancel_step = self._pending_step, self._cancel_step
                    step_count = self._pending_step_count
                if closing:
                    break
                if step is not None:
                    if not step_sent:
                        if cancel_step:
                            with self._lock:
                                self._pending_step = None
                            self.events.put(("step_cancelled", step))
                            continue
                        link.step_once(step, step_count)
                        step_sent = True
                        # At 50 steps/s the largest request (10) takes nominally
                        # 200 ms. This is a reply failure limit, not a timed move.
                        step_deadline = time.monotonic() + 1.0
                        sent = "HOLD"
                        self.events.put(("step_sent", step))
                    if cancel_step and not cancel_sent:
                        link.set_state(mode)
                        sent = mode
                        cancel_sent = True
                    result = link.poll_step_result()
                    if result is not None:
                        with self._lock:
                            self._pending_step = None
                        self.events.put(("step_done" if result == "done" else "step_cancelled", step))
                        step_sent = cancel_sent = False
                        step_deadline = None
                        continue
                    if time.monotonic() >= step_deadline:
                        raise TimeoutError("微調完成回覆逾時；未重送移動，請確認已燒錄新版配套韌體。")
                    self._wake.wait(0.02)
                    continue
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
                self._pending_step = None
            self.events.put(("error" if error else "closed", error or "已送出關閉線圈指令。"))
            self.done.set()
