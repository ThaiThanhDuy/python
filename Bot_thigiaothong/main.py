"""Detect screen(s) resolution and move the mouse in a loop between the
4 corners of the detected screen (a simple "corner macro").

Usage:
    python main.py                  # run on the primary monitor, loop forever
    python main.py --list           # just list detected monitors and exit
    python main.py --monitor 1      # target monitor index 1 (see --list)
    python main.py --loops 5        # stop after 5 full corner cycles
    python main.py --delay 1 --duration 0.8 --margin 10

Press Ctrl+C to stop at any time. As an extra safety net, pyautogui's
fail-safe stays enabled: slamming the real mouse to the screen's true
top-left pixel (x=0, y=0) aborts the script immediately.
"""

import argparse
import sys
import time

import pyautogui

try:
    import screeninfo
    HAS_SCREENINFO = True
except ImportError:
    HAS_SCREENINFO = False


class Monitor:
    def __init__(self, x, y, width, height, name, is_primary):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.name = name
        self.is_primary = is_primary

    def __str__(self):
        primary = " (primary)" if self.is_primary else ""
        return f"{self.name}: {self.width}x{self.height} at ({self.x},{self.y}){primary}"


def detect_monitors():
    """Return a list of Monitor objects for every detected screen."""
    if HAS_SCREENINFO:
        try:
            monitors = screeninfo.get_monitors()
            if monitors:
                return [
                    Monitor(m.x, m.y, m.width, m.height, m.name or f"monitor{i}", m.is_primary)
                    for i, m in enumerate(monitors)
                ]
        except Exception:
            pass  # fall through to the pyautogui fallback below

    width, height = pyautogui.size()
    return [Monitor(0, 0, width, height, "monitor0", True)]


def pick_monitor(monitors, index):
    if index is not None:
        if index < 0 or index >= len(monitors):
            sys.exit(f"--monitor {index} is out of range (0..{len(monitors) - 1})")
        return monitors[index]
    for m in monitors:
        if m.is_primary:
            return m
    return monitors[0]


def corners_of(monitor, margin):
    """4 corner points of the monitor, inset by `margin` pixels so pyautogui's
    fail-safe corner (0,0) is only triggered on purpose by the user."""
    left = monitor.x + margin
    top = monitor.y + margin
    right = monitor.x + monitor.width - 1 - margin
    bottom = monitor.y + monitor.height - 1 - margin
    return [
        (left, top),      # top-left
        (right, top),     # top-right
        (right, bottom),  # bottom-right
        (left, bottom),   # bottom-left
    ]


def run_macro(monitor, loops, delay, duration, margin):
    points = corners_of(monitor, margin)
    print(f"Target: {monitor}")
    print(f"Corners (margin={margin}px): {points}")
    print("Starting in 3 seconds... move the mouse to a screen corner to abort.")
    time.sleep(3)

    count = 0
    try:
        while loops == 0 or count < loops:
            for x, y in points:
                pyautogui.moveTo(x, y, duration=duration)
                time.sleep(delay)
            count += 1
            print(f"Completed loop {count}" + ("" if loops == 0 else f"/{loops}"))
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except pyautogui.FailSafeException:
        print("\nAborted: mouse hit the fail-safe corner (0,0).")


def parse_args():
    parser = argparse.ArgumentParser(description="Detect screen size and move the mouse to its 4 corners.")
    parser.add_argument("--list", action="store_true", help="List detected monitors and exit.")
    parser.add_argument("--monitor", type=int, default=None, help="Monitor index to target (see --list). Default: primary monitor.")
    parser.add_argument("--loops", type=int, default=0, help="Number of corner cycles to run. 0 = run forever (default).")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to pause at each corner (default: 0.5).")
    parser.add_argument("--duration", type=float, default=0.5, help="Seconds for the mouse to travel between corners (default: 0.5).")
    parser.add_argument("--margin", type=int, default=5, help="Pixels to inset from the true corner (default: 5).")
    return parser.parse_args()


def main():
    args = parse_args()
    monitors = detect_monitors()

    if args.list:
        print(f"Detected {len(monitors)} monitor(s):")
        for i, m in enumerate(monitors):
            print(f"  [{i}] {m}")
        return

    monitor = pick_monitor(monitors, args.monitor)
    run_macro(monitor, args.loops, args.delay, args.duration, args.margin)


if __name__ == "__main__":
    main()
