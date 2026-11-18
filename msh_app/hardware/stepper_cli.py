from __future__ import annotations

import argparse
import time

from arduino_stepper import ArduinoStepper, list_serial_ports


def _print_move(move_steps: int, resp: str) -> None:
    print(f"MOVE {move_steps}")
    if resp:
        print(resp)


def _resolve_port(port_arg: str) -> str | None:
    port = (port_arg or "").strip()
    if port:
        return port

    ports = list_serial_ports()
    if not ports:
        print("No serial ports found. Use --list to verify connected devices.")
        return None
    if len(ports) == 1:
        print(f"Auto-selected serial port: {ports[0]}")
        return ports[0]

    print("Multiple serial ports detected. Please specify --port explicitly.")
    for pth in ports:
        print(" ", pth)
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Arduino stepper controller over Serial")
    p.add_argument("--list", action="store_true", help="List serial ports and exit")
    p.add_argument("--port", default="", help="Serial port, e.g. COM3 (leave empty for auto-select)")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--speed_us", type=int, default=800, help="Pulse delay in microseconds (STEP/DIR firmware)")
    p.add_argument("--speed_ms", type=int, default=0, help="Delay per half-step in ms (28BYJ-48 ULN2003 firmware)")
    p.add_argument(
        "--steps",
        type=int,
        default=0,
        help="Relative move steps (can be negative; auto uses as step size)",
    )
    p.add_argument("--auto", action="store_true", help="Run automatic move loop (requires --steps)")
    p.add_argument("--cycles", type=int, default=0, help="Auto moves count (0=forever)")
    p.add_argument("--interval_ms", type=int, default=200, help="Pause between auto moves")
    p.add_argument("--warmup", action="store_true", help="Run small +/- preload moves before normal movement")
    p.add_argument("--warmup_steps", type=int, default=6, help="Warmup half-steps")
    p.add_argument("--warmup_cycles", type=int, default=2, help="Warmup back-and-forth cycles")
    p.add_argument("--fixed_approach", action="store_true", help="End every move from a fixed direction")
    p.add_argument("--approach_direction", type=int, default=1, choices=[-1, 1])
    p.add_argument("--approach_preload_steps", type=int, default=6)
    p.add_argument("--settle_ms", type=int, default=250, help="Wait after stabilized moves")
    p.add_argument(
        "--direction",
        type=int,
        default=1,
        choices=[-1, 1],
        help="Auto direction (1=forward, -1=reverse)",
    )
    p.add_argument(
        "--pingpong",
        action="store_true",
        help="Auto mode: alternate direction each move",
    )
    args = p.parse_args()

    if args.list:
        ports = list_serial_ports()
        if not ports:
            print("No serial ports found")
            return 0
        print("Serial ports:")
        for pth in ports:
            print(" ", pth)
        return 0

    port = _resolve_port(args.port)
    if port is None:
        return 2

    stepper = ArduinoStepper(port=port, baud=args.baud)
    try:
        stepper.connect()
    except Exception as exc:
        print(f"Failed to open serial port {port}: {exc}")
        ports = list_serial_ports()
        if ports:
            print("Available serial ports:")
            for pth in ports:
                print(" ", pth)
        stepper.close()
        return 2
    ok = stepper.ping()
    if not ok:
        print("Warning: no PONG received (check board/baud)")

    if args.speed_ms and args.speed_ms > 0:
        stepper.set_speed_ms(args.speed_ms)
    else:
        stepper.set_speed_us(args.speed_us)
    stepper.default_settle_s = max(0.0, int(args.settle_ms) / 1000.0)

    try:
        if args.warmup:
            stepper.warmup(steps=args.warmup_steps, cycles=args.warmup_cycles)
        if args.auto:
            if args.steps == 0:
                print("Auto mode requires --steps (step size).")
                return 2
            print(
                f"Auto move ready: steps={args.steps} cycles={args.cycles} "
                f"interval_ms={args.interval_ms} direction={args.direction} "
                f"pingpong={int(args.pingpong)}"
            )
            print("Press Ctrl+C to stop.")
            t0 = time.time()
            if args.fixed_approach:
                moves_done = 0
                step_size = abs(int(args.steps))
                dir_sign = 1 if int(args.direction) >= 0 else -1
                if int(args.steps) < 0:
                    dir_sign *= -1
                try:
                    while True:
                        move_steps = step_size * dir_sign
                        resp = stepper.move_with_fixed_approach(
                            move_steps,
                            approach_direction=args.approach_direction,
                            preload_steps=args.approach_preload_steps,
                        )
                        _print_move(move_steps, resp)
                        moves_done += 1
                        if args.pingpong:
                            dir_sign *= -1
                        if int(args.cycles) > 0 and moves_done >= int(args.cycles):
                            break
                        if args.interval_ms > 0:
                            time.sleep(max(0.0, args.interval_ms / 1000.0))
                except KeyboardInterrupt:
                    pass
            else:
                moves_done = stepper.auto_move(
                    steps=args.steps,
                    cycles=int(args.cycles),
                    interval_s=max(0.0, args.interval_ms / 1000.0),
                    direction=int(args.direction),
                    pingpong=bool(args.pingpong),
                    on_move=_print_move,
                )
            elapsed_s = time.time() - t0
            print(f"Auto done: moves={moves_done} elapsed_s={elapsed_s:.2f}")
            return 0

        if args.steps != 0:
            if args.fixed_approach:
                resp = stepper.move_with_fixed_approach(
                    args.steps,
                    approach_direction=args.approach_direction,
                    preload_steps=args.approach_preload_steps,
                )
            else:
                resp = stepper.move_stabilized(args.steps)
            print(resp)
        else:
            print("Connected. No move requested (set --steps)")
        return 0
    finally:
        stepper.close()


if __name__ == "__main__":
    raise SystemExit(main())
