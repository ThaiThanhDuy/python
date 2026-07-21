"""Clickable app: detect screen size and move the mouse to its 4 corners.

Launch by clicking the "Mouse Corner Macro" entry in your application menu
(installed by install_app.sh), or directly with: venv/bin/python gui.py
"""

import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk

import pyautogui

import main as core


def try_fix_xwayland_auth():
    """Best-effort workaround for python-xlib failing to authenticate against
    Mutter's XWayland cookie (GNOME on Wayland). Safe to ignore if it fails."""
    try:
        user = subprocess.getoutput("whoami").strip()
        subprocess.run(["xhost", f"+si:localuser:{user}"], capture_output=True, timeout=3)
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        root.title("Mouse Corner Macro")
        root.resizable(False, False)

        self.stop_event = threading.Event()
        self.worker = None

        self.monitors = core.detect_monitors()
        default_index = next((i for i, m in enumerate(self.monitors) if m.is_primary), 0)

        frame = ttk.Frame(root, padding=12)
        frame.grid()

        row = 0
        ttk.Label(frame, text="Monitor:").grid(row=row, column=0, sticky="w")
        self.monitor_box = ttk.Combobox(
            frame, values=[str(m) for m in self.monitors], state="readonly", width=42
        )
        self.monitor_box.current(default_index)
        self.monitor_box.grid(row=row, column=1, columnspan=2, sticky="we", pady=2)

        row += 1
        ttk.Label(frame, text="Delay giữa các góc (s):").grid(row=row, column=0, sticky="w")
        self.delay_var = tk.StringVar(value="0.5")
        ttk.Entry(frame, textvariable=self.delay_var, width=10).grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(frame, text="Thời gian di chuyển (s):").grid(row=row, column=0, sticky="w")
        self.duration_var = tk.StringVar(value="0.5")
        ttk.Entry(frame, textvariable=self.duration_var, width=10).grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(frame, text="Margin (px):").grid(row=row, column=0, sticky="w")
        self.margin_var = tk.StringVar(value="5")
        ttk.Entry(frame, textvariable=self.margin_var, width=10).grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(frame, text="Số vòng lặp (0 = vô hạn):").grid(row=row, column=0, sticky="w")
        self.loops_var = tk.StringVar(value="0")
        ttk.Entry(frame, textvariable=self.loops_var, width=10).grid(row=row, column=1, sticky="w")

        row += 1
        btns = ttk.Frame(frame)
        btns.grid(row=row, column=0, columnspan=3, pady=(10, 0))
        self.start_btn = ttk.Button(btns, text="Start", command=self.start)
        self.start_btn.grid(row=0, column=0, padx=4)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=4)

        row += 1
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(frame, textvariable=self.status_var, foreground="#555").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def start(self):
        try:
            delay = float(self.delay_var.get())
            duration = float(self.duration_var.get())
            margin = int(self.margin_var.get())
            loops = int(self.loops_var.get())
        except ValueError:
            self.status_var.set("Giá trị nhập không hợp lệ.")
            return

        monitor = self.monitors[self.monitor_box.current()]
        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.monitor_box.config(state="disabled")

        self.worker = threading.Thread(
            target=self.run_macro,
            args=(monitor, loops, delay, duration, margin),
            daemon=True,
        )
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.status_var.set("Đang dừng...")

    def run_macro(self, monitor, loops, delay, duration, margin):
        points = core.corners_of(monitor, margin)
        self.set_status(f"Bắt đầu sau 2 giây trên {monitor.name}...")
        if self.wait_cancelable(2.0):
            self.set_status("Đã dừng.")
            self.root.after(0, self.on_finished)
            return

        count = 0
        try:
            while loops == 0 or count < loops:
                for x, y in points:
                    if self.stop_event.is_set():
                        self.set_status("Đã dừng.")
                        return
                    pyautogui.moveTo(x, y, duration=duration)
                    if self.wait_cancelable(delay):
                        self.set_status("Đã dừng.")
                        return
                count += 1
                self.set_status(f"Đã chạy {count}" + ("" if loops == 0 else f"/{loops}") + " vòng.")
            self.set_status(f"Hoàn tất {count} vòng.")
        except pyautogui.FailSafeException:
            self.set_status("Đã dừng khẩn cấp (chuột chạm góc 0,0).")
        except Exception as exc:
            self.set_status(f"Lỗi: {exc}")
        finally:
            self.root.after(0, self.on_finished)

    def wait_cancelable(self, seconds):
        """Sleep in small steps so Stop reacts quickly. Returns True if canceled."""
        end = time.time() + seconds
        while time.time() < end:
            if self.stop_event.is_set():
                return True
            time.sleep(min(0.05, max(0.0, end - time.time())))
        return False

    def set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def on_finished(self):
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.monitor_box.config(state="readonly")

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()


def main():
    try_fix_xwayland_auth()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
