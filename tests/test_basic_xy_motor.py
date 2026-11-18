"""Test the minimal ConstantSpeed GUI/serial adapter without real hardware."""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
import unittest
from types import SimpleNamespace
from unittest import mock

from msh_app.hardware.basic_xy import BasicXYLink, BasicXYSession
from msh_app.hardware.basic_motor_gui import BasicMotorGUI


class SerialBoard:
    def __init__(self):
        self.commands = []
        self.closed = False
        self.write_error = False

    def write(self, data):
        self.commands.append(data)
        if self.write_error:
            raise OSError("USB lost")
        return len(data)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def make_link(self, board):
        return BasicXYLink("COM_FAKE", serial_factory=lambda *a, **k: board, boot_wait=0)

    def test_connect_does_not_send_identity_speed_or_motion_commands(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        self.assertEqual(board.commands, [])
        link.shutdown()
        self.assertEqual(board.commands, [b"q"])

    def test_four_directions_stop_and_close_use_only_button_commands(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        for mode in ("X+", "X-", "Y+", "Y-", "HOLD"):
            link.set_state(mode)
        link.shutdown()
        self.assertEqual(board.commands, [b"a", b"b", b"c", b"d", b"s", b"q"])
        self.assertTrue(board.closed)

    def test_invalid_mode_does_not_write(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        with self.assertRaises(ValueError):
            link.set_state("X+ Y+")
        self.assertEqual(board.commands, [])
        link.shutdown()

    def test_write_failure_is_not_retried_and_shutdown_closes_port(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        board.write_error = True
        with self.assertRaises(OSError):
            link.set_state("X+")
        with self.assertRaises(OSError):
            link.shutdown()
        self.assertEqual(board.commands, [b"a", b"q"])
        self.assertTrue(board.closed)


class WorkerLink:
    def __init__(self):
        self.calls = []
        self.mode_seen = threading.Event()
        self.connect_started = threading.Event()
        self.allow_connect = threading.Event()
        self.allow_connect.set()
        self.close_error = False

    def connect(self):
        self.connect_started.set()
        if not self.allow_connect.wait(2):
            raise TimeoutError("test connect gate")
        self.calls.append((threading.get_ident(), "connect"))

    def set_state(self, mode):
        self.calls.append((threading.get_ident(), mode))
        self.mode_seen.set()

    def shutdown(self):
        self.calls.append((threading.get_ident(), "close"))
        if self.close_error:
            raise OSError("USB lost")


class SessionTests(unittest.TestCase):
    def wait_for(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("Worker did not reach the expected state")
            time.sleep(0.005)

    def test_single_worker_sends_changes_without_idle_retransmission(self):
        link = WorkerLink()
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        try:
            self.wait_for(link.mode_seen.is_set)
            session.request("X+")
            self.wait_for(lambda: link.calls[-1][1] == "X+")
            calls_before_wait = list(link.calls)
            session.request("X+")
            # Repeated press events and idle time must not renew/replay motion.
            time.sleep(0.3)
            self.assertEqual(link.calls, calls_before_wait)
            session.request("HOLD")
            self.wait_for(lambda: link.calls[-1][1] == "HOLD")
        finally:
            session.close()
            self.assertTrue(session.done.wait(2))
        self.assertEqual(link.calls[-1][1], "close")
        self.assertEqual(len({owner for owner, _ in link.calls}), 1)
        self.assertNotEqual(link.calls[0][0], threading.get_ident())

    def test_close_during_connection_never_starts_motion(self):
        link = WorkerLink()
        link.allow_connect.clear()
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        self.assertTrue(link.connect_started.wait(1))
        session.close()
        session.request("X+")
        link.allow_connect.set()
        self.assertTrue(session.done.wait(2))
        self.assertEqual([c for _, c in link.calls], ["connect", "close"])

    def test_factory_failure_finishes_session(self):
        def fail(_port):
            raise OSError("factory error")
        session = BasicXYSession(link_factory=fail)
        session.connect("COM_FAKE")
        self.assertTrue(session.done.wait(2))
        self.assertEqual(session.events.get_nowait(), ("error", "factory error"))

    def test_close_failure_reports_need_to_remove_power(self):
        link = WorkerLink()
        link.close_error = True
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        self.wait_for(link.mode_seen.is_set)
        session.close()
        self.assertTrue(session.done.wait(2))
        self.assertTrue(any(kind == "error" and "手動切斷馬達電源" in text
                            for kind, text in session.events.queue))


class GuiSession:
    def __init__(self):
        self.events = queue.Queue()
        self.done = threading.Event()
        self.done.set()
        self.requests = []
        self.close_requested = False
        self.port = None

    def connect(self, port):
        self.port = port
        self.done.clear()

    def request(self, mode):
        self.requests.append(mode)

    def close(self):
        self.close_requested = True


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.session = GuiSession()
        self.gui = BasicMotorGUI(self.root, session=self.session,
                                 port_provider=lambda: [SimpleNamespace(device="COM_FAKE")])

    def tearDown(self):
        try:
            self.root.after_cancel(self.gui._tick_id)
            self.root.destroy()
        except tk.TclError:
            pass

    def connected(self):
        self.gui.port_var.set("COM_FAKE")
        self.gui._connect()
        self.session.events.put(("connected", "COM_FAKE"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()

    def test_no_auto_port_selection_and_four_motion_buttons_only(self):
        self.assertEqual(self.gui.port_var.get(), "")
        self.assertEqual(set(self.gui.motion_buttons), {"X+", "X-", "Y+", "Y-"})
        labels = []
        def visit(widget):
            if isinstance(widget, ttk.Button):
                labels.append(widget.cget("text"))
            for child in widget.winfo_children():
                visit(child)
        visit(self.root)
        self.assertEqual(set(labels), {"重新整理", "連線", "X 前進", "X 後退", "Y 前進", "Y 後退"})
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in self.gui.motion_buttons.values()))

    def test_four_buttons_request_correct_mode_and_release_holds(self):
        self.connected()
        for mode in self.gui.motion_buttons:
            self.gui._press(mode)
            self.gui._stop()
        self.assertEqual(self.session.requests, ["X+", "HOLD", "X-", "HOLD", "Y+", "HOLD", "Y-", "HOLD"])

    def test_late_leave_from_old_button_cannot_cancel_new_button(self):
        self.connected()
        self.gui._press("X+")
        self.gui._press("Y-")
        self.gui._leave("X+")
        self.assertEqual(self.session.requests, ["X+", "Y-"])
        self.gui._leave("Y-")
        self.assertEqual(self.session.requests[-1], "HOLD")

    def test_widget_focus_transfer_does_not_cancel_a_held_direction(self):
        self.connected()
        self.gui._press("X+")
        with mock.patch.object(self.root, "focus_displayof", return_value=self.gui.port_combo):
            self.gui._stop_if_unfocused()
        self.assertEqual(self.session.requests, ["X+"])
        with mock.patch.object(self.root, "focus_displayof", return_value=None):
            self.gui._stop_if_unfocused()
        self.assertEqual(self.session.requests, ["X+", "HOLD"])

    def test_mouse_bindings_dispatch_press_release_and_leave(self):
        self.connected()
        for mode, button in self.gui.motion_buttons.items():
            button.event_generate("<ButtonPress-1>", x=4, y=4)
            self.assertEqual(self.session.requests[-1], mode)
            button.event_generate("<ButtonRelease-1>", x=4, y=4)
            self.assertEqual(self.session.requests[-1], "HOLD")
            button.event_generate("<ButtonPress-1>", x=4, y=4)
            button.event_generate("<Leave>")
            self.assertEqual(self.session.requests[-1], "HOLD")

    def test_close_waits_for_worker_and_cannot_restart_motion(self):
        self.connected()
        self.gui.close()
        self.gui._press("X+")
        self.assertTrue(self.session.close_requested)
        self.assertFalse(self.session.done.is_set())
        self.assertEqual(self.session.requests, [])
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in self.gui.motion_buttons.values()))
        self.session.events.put(("closed", "線圈輸出已關閉。"))
        self.session.done.set()
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        with self.assertRaises(tk.TclError):
            self.root.winfo_exists()


if __name__ == "__main__":
    unittest.main()
