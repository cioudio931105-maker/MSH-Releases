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
        self.reply = b""

    def write(self, data):
        self.commands.append(data)
        if self.write_error:
            raise OSError("USB lost")
        return len(data)

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.reply = b""

    def read(self, size):
        result, self.reply = self.reply[:size], self.reply[size:]
        return result

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

    def test_each_single_step_direction_is_one_finite_command(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        for mode in ("X+", "X-", "Y+", "Y-"):
            link.step_once(mode)
        self.assertEqual(board.commands, [b"A", b"B", b"C", b"D"])
        with self.assertRaises(ValueError):
            link.step_once("HOLD")
        link.shutdown()

    def test_step_completion_handles_split_replies_and_cancellation(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        link.step_once("X+")
        board.reply = b"STEP DO"
        self.assertIsNone(link.poll_step_result())
        board.reply = b"NE\r\n"
        self.assertEqual(link.poll_step_result(), "done")
        link.step_once("Y-")
        board.reply = b"STEP CANCELLED\n"
        self.assertEqual(link.poll_step_result(), "cancelled")
        link.shutdown()

    def test_five_and_ten_step_commands_do_not_repeat_single_step_bytes(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        for count in (5, 10):
            for mode in ("X+", "X-", "Y+", "Y-"):
                link.step_once(mode, count)
        self.assertEqual(board.commands, [b"E", b"F", b"G", b"H", b"I", b"J", b"K", b"L"])
        for invalid in (0, 2, 50, True, 5.0, "5"):
            with self.assertRaises(ValueError):
                link.step_once("X+", invalid)
        self.assertEqual(len(board.commands), 8)
        link.shutdown()

    def test_stale_completion_cannot_complete_the_next_step(self):
        board = SerialBoard()
        link = self.make_link(board)
        link.connect()
        board.reply = b"STEP DONE\n"
        link.step_once("X+")
        self.assertIsNone(link.poll_step_result())
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
        self.step_results = queue.Queue()

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

    def step_once(self, mode, steps=1):
        suffix = "" if steps == 1 else f" {steps}"
        self.calls.append((threading.get_ident(), "STEP " + mode + suffix))

    def poll_step_result(self):
        try:
            return self.step_results.get_nowait()
        except queue.Empty:
            return None


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
        self.assertFalse(session.request_step("Y-"))
        link.allow_connect.set()
        self.assertTrue(session.done.wait(2))
        self.assertEqual([c for _, c in link.calls], ["connect", "close"])

    def test_single_steps_wait_for_completion_and_never_queue_or_repeat(self):
        link = WorkerLink()
        session = BasicXYSession(link_factory=lambda p: link)
        self.assertFalse(session.request_step("X+"))
        session.connect("COM_FAKE")
        try:
            self.wait_for(link.mode_seen.is_set)
            self.assertTrue(session.request_step("X+"))
            self.wait_for(lambda: link.calls[-1][1] == "STEP X+")
            for _ in range(20):
                self.assertFalse(session.request_step("Y-"))
            self.assertEqual([c for _, c in link.calls if c.startswith("STEP")], ["STEP X+"])
            link.step_results.put("done")
            self.wait_for(lambda: any(kind == "step_done" for kind, _ in session.events.queue))
            self.assertTrue(session.request_step("X+"))
            self.wait_for(lambda: len([c for _, c in link.calls if c == "STEP X+"]) == 2)
            link.step_results.put("done")
            self.wait_for(lambda: sum(kind == "step_done" for kind, _ in session.events.queue) == 2)
        finally:
            session.close()
            self.assertTrue(session.done.wait(2))
        self.assertEqual(len({owner for owner, _ in link.calls}), 1)

    def test_stop_cancels_pending_step_without_replaying_it(self):
        link = WorkerLink()
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        try:
            self.wait_for(link.mode_seen.is_set)
            self.assertTrue(session.request_step("X+"))
            self.wait_for(lambda: link.calls[-1][1] == "STEP X+")
            session.request("HOLD")
            self.wait_for(lambda: link.calls[-1][1] == "HOLD")
            self.assertFalse(session.request_step("Y+"))
            link.step_results.put("cancelled")
            self.wait_for(lambda: any(kind == "step_cancelled" for kind, _ in session.events.queue))
            self.assertEqual([c for _, c in link.calls if c.startswith("STEP")], ["STEP X+"])
        finally:
            session.close()
            self.assertTrue(session.done.wait(2))

    def test_step_cancelled_before_dispatch_is_never_sent(self):
        link = WorkerLink()
        initial_hold = threading.Event()
        release_hold = threading.Event()
        original_set_state = link.set_state

        def gated_hold(mode):
            original_set_state(mode)
            if mode == "HOLD" and not initial_hold.is_set():
                initial_hold.set()
                if not release_hold.wait(2):
                    raise TimeoutError("test initial hold gate")

        link.set_state = gated_hold
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        try:
            self.assertTrue(initial_hold.wait(1))
            self.assertTrue(session.request_step("X+"))
            session.request("HOLD")
            release_hold.set()
            self.wait_for(lambda: any(kind == "step_cancelled" for kind, _ in session.events.queue))
            self.assertFalse(any(c.startswith("STEP") for _, c in link.calls))
        finally:
            release_hold.set()
            session.close()
            self.assertTrue(session.done.wait(2))

    def test_selected_count_is_captured_and_extra_requests_do_not_queue(self):
        link = WorkerLink()
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        try:
            self.wait_for(link.mode_seen.is_set)
            with self.assertRaises(ValueError):
                session.request_step("X+", 100)
            self.assertTrue(session.request_step("X+", 5))
            self.wait_for(lambda: link.calls[-1][1] == "STEP X+ 5")
            self.assertFalse(session.request_step("X+", 10))
            link.step_results.put("done")
            self.wait_for(lambda: any(kind == "step_done" for kind, _ in session.events.queue))
            self.assertTrue(session.request_step("Y-", 10))
            self.wait_for(lambda: link.calls[-1][1] == "STEP Y- 10")
            self.assertEqual([c for _, c in link.calls if c.startswith("STEP")], ["STEP X+ 5", "STEP Y- 10"])
            link.step_results.put("done")
        finally:
            session.close()
            self.assertTrue(session.done.wait(2))

    def test_close_while_waiting_for_step_does_not_wait_for_reply_or_replay(self):
        link = WorkerLink()
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        self.wait_for(link.mode_seen.is_set)
        self.assertTrue(session.request_step("Y-"))
        self.wait_for(lambda: link.calls[-1][1] == "STEP Y-")
        session.close()
        self.assertFalse(session.request_step("Y-"))
        self.assertTrue(session.done.wait(1))
        self.assertEqual(link.calls[-1][1], "close")
        self.assertEqual([c for _, c in link.calls if c.startswith("STEP")], ["STEP Y-"])

    def test_missing_firmware_reply_stops_session_without_resending(self):
        link = WorkerLink()
        session = BasicXYSession(link_factory=lambda p: link)
        session.connect("COM_FAKE")
        self.wait_for(link.mode_seen.is_set)
        self.assertTrue(session.request_step("X-"))
        self.assertTrue(session.done.wait(2))
        self.assertEqual([c for _, c in link.calls if c.startswith("STEP")], ["STEP X-"])
        self.assertEqual(link.calls[-1][1], "close")
        self.assertTrue(any(kind == "error" and "逾時" in text for kind, text in session.events.queue))

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
        self.steps = []

    def connect(self, port):
        self.port = port
        self.done.clear()

    def request(self, mode):
        self.requests.append(mode)

    def request_step(self, mode, steps=1):
        self.steps.append((mode, steps))
        return True

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
        self.assertEqual(self.gui.motion_mode.get(), "step")
        self.assertEqual(self.gui.step_count_var.get(), "5")
        self.assertEqual(tuple(self.gui.step_count_combo.cget("values")), ("5", "10"))
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
        self.gui.motion_mode.set("continuous")
        for mode in self.gui.motion_buttons:
            self.gui._press(mode)
            self.gui._stop()
        self.assertEqual(self.session.requests, ["X+", "HOLD", "X-", "HOLD", "Y+", "HOLD", "Y-", "HOLD"])

    def test_late_leave_from_old_button_cannot_cancel_new_button(self):
        self.connected()
        self.gui.motion_mode.set("continuous")
        self.gui._press("X+")
        self.gui._press("Y-")
        self.gui._leave("X+")
        self.assertEqual(self.session.requests, ["X+", "Y-"])
        self.gui._leave("Y-")
        self.assertEqual(self.session.requests[-1], "HOLD")

    def test_widget_focus_transfer_does_not_cancel_a_held_direction(self):
        self.connected()
        self.gui.motion_mode.set("continuous")
        self.gui._press("X+")
        with mock.patch.object(self.root, "focus_displayof", return_value=self.gui.port_combo):
            self.gui._stop_if_unfocused()
        self.assertEqual(self.session.requests, ["X+"])
        with mock.patch.object(self.root, "focus_displayof", return_value=None):
            self.gui._stop_if_unfocused()
        self.assertEqual(self.session.requests, ["X+", "HOLD"])

    def test_mouse_bindings_dispatch_press_release_and_leave(self):
        self.connected()
        self.gui.motion_mode.set("continuous")
        for mode, button in self.gui.motion_buttons.items():
            button.event_generate("<ButtonPress-1>", x=4, y=4)
            self.assertEqual(self.session.requests[-1], mode)
            button.event_generate("<ButtonRelease-1>", x=4, y=4)
            self.assertEqual(self.session.requests[-1], "HOLD")
            button.event_generate("<ButtonPress-1>", x=4, y=4)
            button.event_generate("<Leave>")
            self.assertEqual(self.session.requests[-1], "HOLD")

    def test_step_click_does_not_repeat_on_hold_or_release(self):
        self.connected()
        self.gui._press("X+")
        self.gui._press("X+")
        self.assertEqual(self.session.steps, [("X+", 5)])
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in self.gui.motion_buttons.values()))
        self.gui._release()
        self.gui._press("Y-")
        self.assertEqual(self.session.steps, [("X+", 5)])
        self.assertEqual(self.session.requests, [])
        self.session.events.put(("step_done", "X+"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        self.gui._press("X+")
        self.assertEqual(self.session.steps, [("X+", 5), ("X+", 5)])

    def test_completion_while_button_held_still_requires_a_new_click(self):
        self.connected()
        self.gui._press("Y+")
        self.session.events.put(("step_done", "Y+"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        self.gui._press("Y+")
        self.assertEqual(self.session.steps, [("Y+", 5)])
        self.gui._release()
        self.gui._press("Y+")
        self.assertEqual(self.session.steps, [("Y+", 5), ("Y+", 5)])

    def test_step_mouse_release_is_delivered_after_button_is_disabled(self):
        self.connected()
        button = self.gui.motion_buttons["X+"]
        button.event_generate("<ButtonPress-1>", x=4, y=4)
        self.assertEqual(self.session.steps, [("X+", 5)])
        button.event_generate("<ButtonRelease-1>", x=4, y=4)
        self.assertEqual(self.session.requests, [])
        self.session.events.put(("step_done", "X+"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        button.event_generate("<ButtonPress-1>", x=4, y=4)
        button.event_generate("<ButtonRelease-1>", x=4, y=4)
        self.assertEqual(self.session.steps, [("X+", 5), ("X+", 5)])

    def test_mode_change_stops_pending_step_and_awaits_cancel_reply(self):
        self.connected()
        self.gui._press("X-")
        self.gui.motion_mode.set("continuous")
        self.gui._change_mode()
        self.assertEqual(self.session.requests, ["HOLD"])
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in self.gui.motion_buttons.values()))
        # Tk widget bindings can still receive events while ttk is disabled.
        self.gui.motion_buttons["Y+"].event_generate("<ButtonPress-1>", x=4, y=4)
        self.assertEqual(self.session.requests, ["HOLD"])
        self.session.events.put(("step_cancelled", "X-"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        self.assertTrue(all(str(b.cget("state")) == "normal" for b in self.gui.motion_buttons.values()))

    def test_step_error_keeps_motion_disabled_and_restores_connection_controls(self):
        self.connected()
        self.gui._press("X+")
        self.session.events.put(("error", "微調完成回覆逾時"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        self.gui._press("Y+")
        self.assertEqual(self.session.steps, [("X+", 5)])
        self.assertTrue(all(str(b.cget("state")) == "disabled" for b in self.gui.motion_buttons.values()))
        self.assertEqual(str(self.gui.connect_button.cget("state")), "normal")

    def test_count_selection_is_disabled_until_done_and_status_uses_submitted_count(self):
        self.connected()
        self.gui.step_count_var.set("10")
        self.gui._press("Y-")
        self.assertEqual(self.session.steps, [("Y-", 10)])
        self.assertEqual(str(self.gui.step_count_combo.cget("state")), "disabled")
        # A later variable change must not relabel the completed request.
        self.gui.step_count_var.set("5")
        self.session.events.put(("step_done", "Y-"))
        self.root.after_cancel(self.gui._tick_id)
        self.gui._tick()
        self.assertIn("10 整步", self.gui.status_var.get())
        self.assertEqual(str(self.gui.step_count_combo.cget("state")), "readonly")

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
