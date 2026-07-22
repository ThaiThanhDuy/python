"""Clickable app: detects on-screen quiz questions/answers via OCR and logs
them (with their screen coordinates) to detected_questions.json. Also keeps
the original mouse-corner/capture-point macro as a separate feature (tab Test).

Launch by clicking the "Mouse Corner Macro" entry in your Start Menu
(installed by install_app.bat), or directly with: venv\\Scripts\\python gui.py
"""

import difflib
import json
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import unicodedata
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import imagehash
import numpy as np
import pyautogui
from PIL import Image, ImageGrab, ImageTk
from pynput import mouse as pynput_mouse
from pynput import keyboard as pynput_keyboard

import main as core


def normalize_for_match(text):
    """Bỏ dấu tiếng Việt + hạ chữ thường, CHỈ dùng để so khớp mẫu (không
    dùng để lưu/hiển thị). OCR hay đọc sai/lẫn dấu thanh ("hỏi" -> "hòi"/
    "hối"...) hoặc thêm/bớt khoảng trắng quanh dấu câu — so khớp trên bản đã
    bỏ dấu giúp nhận diện đúng header câu hỏi ngay cả khi dấu bị đọc sai,
    thay vì đòi khớp tuyệt đối ký tự có dấu."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.lower()


# Marks the generic header shown above each question on trang "Kiểm tra",
# e.g. "1. Câu hỏi chọn một đáp án" / "2. Câu hỏi chọn nhiều đáp án". So khớp
# trên text đã bỏ dấu (xem normalize_for_match) để không bị hỏng vì OCR đọc
# sai dấu thanh của "hỏi", cho phép có khoảng trắng thừa quanh dấu chấm
# ("8 . Câu hỏi...") vì OCR đôi khi tách dấu chấm ra thành 1 "chữ" riêng, và
# dấu chấm là TÙY CHỌN vì OCR nhiều khi đọc rớt mất hẳn dấu chấm nhỏ xíu đó
# (vd đọc "9 Câu hỏi..." không có dấu chấm nào) - từng khiến cả câu hỏi bị bỏ
# qua hoàn toàn (log báo "Không tìm thấy câu hỏi nào").
QUESTION_HEADER_PATTERN = re.compile(r"^\d+\s*\.?\s*cau\s*hoi")

# Marks a numbered answer-option line, e.g. "1-Đúng.", "2-Không đúng.".
ANSWER_OPTION_PATTERN = re.compile(r"^\d+[-.]\s*\S")

# Where detected questions/answers + their on-screen coordinates are saved.
OCR_RECORDS_PATH = Path(__file__).resolve().parent / "detected_questions.json"

# Where cropped question-illustration images are saved, named by their hash.
QUESTION_IMAGES_DIR = Path(__file__).resolve().parent / "question_images"


def try_fix_xwayland_auth():
    """Best-effort workaround for python-xlib failing to authenticate against
    Mutter's XWayland cookie (GNOME on Wayland). Linux/X11 only; no-op elsewhere."""
    if not sys.platform.startswith("linux"):
        return
    try:
        user = subprocess.getoutput("whoami").strip()
        subprocess.run(
            ["xhost", f"+si:localuser:{user}"], capture_output=True, timeout=3
        )
    except Exception:
        pass


def apply_noactivate_style(hwnd):
    """Đánh dấu cửa sổ (vd overlay log) là 'không kích hoạt': luôn hiện đè
    lên trên (topmost) nhưng không bao giờ cướp focus bàn phím/chuyển nó
    thành cửa sổ đang active, kể cả khi vừa tạo ra hay bị bấm vào - để
    tránh kích hoạt tính năng chống gian lận của web (phát hiện rời màn
    hình) khi người dùng vẫn đang thao tác trên trình duyệt."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )
    except Exception:
        pass


def remove_window_icon(root):
    """Strip the default tk 'feather' icon from the title bar/taskbar on
    Windows, keeping normal window chrome (minimize/maximize/close)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        WM_SETICON = 0x0080
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, 0)  # ICON_SMALL
        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, 0)  # ICON_BIG
    except Exception:
        pass


class App:
    # Kích thước "gốc" (ứng với cửa sổ chưa phóng to) của cột #0 trong tab
    # Data - dùng làm mốc để tính tỉ lệ phóng to chữ/ảnh khi Maximize cửa sổ.
    DATA_TREE_BASE_WIDTH = 610
    DATA_TREE_BASE_ROWHEIGHT = 20
    DATA_TREE_BASE_FONT_SIZE = 9
    DATA_TREE_BASE_THUMB = 48
    DATA_TREE_BASE_INDICATOR = 9
    DATA_TREE_MAX_SCALE = 3.0

    def __init__(self, root):
        self.root = root
        root.title("Bot thi giao thông")
        root.resizable(True, True)  # cho phép kéo giãn / bấm nút vuông (Maximize) để phóng to

        self.stop_event = threading.Event()
        self.worker = None

        self.captured_points = []
        self.capturing = False
        self.mouse_listener = None
        self.keyboard_listener = None
        self.hotkey_listener = None

        self.log_overlay = None
        self.log_overlay_text = None

        self.ocr_reader = None
        self.ocr_records = {}  # question text -> record, mirrors OCR_RECORDS_PATH
        self.detect_armed = False  # True sau khi bấm Start; Ctrl+Shift+Q chỉ hoạt động khi True
        self._detect_one_busy = False

        self.tool_thread = None
        self.tool_stop_event = threading.Event()
        self._last_tool_frame_sig = None

        self.monitors = core.detect_monitors()
        default_index = next(
            (i for i, m in enumerate(self.monitors) if m.is_primary), 0
        )

        self.notebook = notebook = ttk.Notebook(root)
        notebook.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 0))

        tool_tab = ttk.Frame(notebook, padding=12)
        app_tab = ttk.Frame(notebook, padding=12)
        self.data_tab = data_tab = ttk.Frame(notebook, padding=12)
        test_tab = ttk.Frame(notebook, padding=12)
        notebook.add(tool_tab, text="Tool")
        notebook.add(app_tab, text="App")
        notebook.add(data_tab, text="Data")
        notebook.add(test_tab, text="Test")

        # --- Tab "Tool": đối chiếu đáp án đúng đã lưu và tự click ---
        row = 0
        ttk.Label(tool_tab, text="Chu kỳ quét (s):").grid(row=row, column=0, sticky="w")
        self.tool_interval_var = tk.StringVar(value="1")
        ttk.Entry(tool_tab, textvariable=self.tool_interval_var, width=10).grid(
            row=row, column=1, sticky="w"
        )

        row += 1
        ttk.Label(tool_tab, text="Cách lề trái đáp án (px):").grid(
            row=row, column=0, sticky="w"
        )
        self.tool_offset_var = tk.StringVar(value="30")
        ttk.Entry(tool_tab, textvariable=self.tool_offset_var, width=10).grid(
            row=row, column=1, sticky="w"
        )

        row += 1
        tool_btns = ttk.Frame(tool_tab)
        tool_btns.grid(row=row, column=0, columnspan=3, pady=(10, 0))
        self.tool_start_btn = ttk.Button(
            tool_btns, text="Start", command=self.start_tool
        )
        self.tool_start_btn.grid(row=0, column=0, padx=4)
        self.tool_stop_btn = ttk.Button(
            tool_btns, text="Stop", command=self.stop_tool, state="disabled"
        )
        self.tool_stop_btn.grid(row=0, column=1, padx=4)

        row += 1
        self.tool_status_var = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(tool_tab, textvariable=self.tool_status_var, foreground="#555").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        # --- Tab "App": Detect màn hình (OCR) + ghi dữ liệu ---
        # Start chỉ khởi động (nạp sẵn model OCR cho nhanh) chứ KHÔNG tự quét
        # liên tục - quét từng câu một hoàn toàn thủ công qua Ctrl+Shift+Q để
        # bạn chủ động chọn đúng lúc câu hỏi đã hiện đủ trên màn hình, tránh
        # ghi nhầm ảnh/nội dung của câu trước/câu đang load dở.
        row = 0
        ttk.Label(
            app_tab,
            text=(
                "Start: khởi động (nạp OCR, chưa quét).\n"
                "Ctrl+Shift+Q: detect đúng 1 câu hỏi + đáp án + ảnh đang hiện."
            ),
            foreground="#555",
            justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="w")

        row += 1
        btns = ttk.Frame(app_tab)
        btns.grid(row=row, column=0, columnspan=3, pady=(10, 0))
        self.start_btn = ttk.Button(
            btns, text="Start (Ctrl+Shift+S)", command=self.start_detect_and_record
        )
        self.start_btn.grid(row=0, column=0, padx=4)
        self.stop_btn = ttk.Button(
            btns,
            text="Stop (Ctrl+Shift+E)",
            command=self.stop_detect_and_record,
            state="disabled",
        )
        self.stop_btn.grid(row=0, column=1, padx=4)
        self.detect_one_btn = ttk.Button(
            btns, text="Detect 1 câu (Ctrl+Shift+Q)", command=self.trigger_detect_one
        )
        self.detect_one_btn.grid(row=0, column=2, padx=4)

        row += 1
        self.status_var = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(app_tab, textvariable=self.status_var, foreground="#555").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )

        # --- Tab "Data": xem detected_questions.json dạng bảng ---
        row = 0
        data_top = ttk.Frame(data_tab)
        data_top.grid(row=row, column=0, sticky="we")
        self.data_count_var = tk.StringVar(value="0 câu hỏi.")
        ttk.Label(data_top, textvariable=self.data_count_var, foreground="#555").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(data_top, text="Làm mới", command=self.refresh_data_tab).grid(
            row=0, column=1, padx=(10, 0)
        )
        ttk.Button(data_top, text="Lưu", command=self.save_data_records).grid(
            row=0, column=2, padx=(6, 0)
        )
        ttk.Button(
            data_top, text="Xóa", command=self.delete_selected_data_records
        ).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(
            data_top, text="Xóa hết", command=self.delete_all_data_records
        ).grid(row=0, column=4, padx=(6, 0))
        self.filter_btn = ttk.Button(
            data_top, text="Lọc trùng lặp", command=self.check_duplicate_questions
        )
        self.filter_btn.grid(row=0, column=5, padx=(6, 0))

        row += 1
        ttk.Label(
            data_tab,
            text=(
                "Tích ☐→☑ trước đáp án rồi bấm Lưu để đánh dấu đáp án đúng.\n"
                "Tích ☐→☑ trước câu hỏi rồi bấm Xóa để xóa (các) câu hỏi đó."
            ),
            foreground="#555",
            justify="left",
        ).grid(row=row, column=0, sticky="w", pady=(4, 0))

        row += 1
        tree_frame = ttk.Frame(data_tab)
        tree_frame.grid(row=row, column=0, sticky="nsew", pady=(8, 0))
        # Phóng to cửa sổ (nút vuông Maximize) -> danh sách câu hỏi giãn to ra
        # theo, thấy rõ hình/câu hỏi/đáp án hơn thay vì bị kẹt cứng ở góc.
        data_tab.columnconfigure(0, weight=1)
        data_tab.rowconfigure(row, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.data_tree_style = ttk.Style()
        self.data_tree_style.configure(
            "Data.Treeview",
            rowheight=self.DATA_TREE_BASE_ROWHEIGHT,
            indicatorsize=self.DATA_TREE_BASE_INDICATOR,
        )
        # Theme mặc định trên Windows ("vista") vẽ dấu +/- bằng glyph hệ
        # điều hành kích thước CỐ ĐỊNH, không co giãn theo indicatorsize hay
        # rowheight. Mượn (borrow) phần tử indicator từ theme "clam" - vốn tự
        # vẽ bằng ttk nên NGHE indicatorsize - rồi gán vào layout riêng cho
        # Data.Treeview, để dấu +/- to ra cùng tỉ lệ với chữ/ảnh khi phóng to.
        try:
            self.data_tree_style.element_create(
                "Data.Treeitem.indicator", "from", "clam"
            )
        except tk.TclError:
            pass  # đã tạo từ trước (vd App() được dựng lại trong cùng tiến trình)
        self.data_tree_style.layout(
            "Data.Treeview.Item",
            [
                (
                    "Treeitem.padding",
                    {
                        "sticky": "nswe",
                        "children": [
                            ("Data.Treeitem.indicator", {"side": "left", "sticky": ""}),
                            ("Treeitem.image", {"side": "left", "sticky": ""}),
                            ("Treeitem.text", {"sticky": "nswe"}),
                        ],
                    },
                )
            ],
        )
        self.data_tree = ttk.Treeview(
            tree_frame, show="tree", height=16, style="Data.Treeview"
        )
        self.data_tree.column("#0", width=self.DATA_TREE_BASE_WIDTH, anchor="w")
        self.data_tree.tag_configure(
            "question", font=("TkDefaultFont", self.DATA_TREE_BASE_FONT_SIZE, "bold")
        )
        self.data_tree.tag_configure(
            "answer", font=("TkDefaultFont", self.DATA_TREE_BASE_FONT_SIZE)
        )
        self.data_tree.bind("<Button-1>", self.on_data_tree_click)

        data_vsb = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.data_tree.yview
        )
        self.data_tree.configure(yscrollcommand=data_vsb.set)
        self.data_tree.grid(row=0, column=0, sticky="nsew")
        data_vsb.grid(row=0, column=1, sticky="ns")

        # Câu hỏi/ảnh/đáp án tự phóng to theo khung trắng khi cửa sổ được
        # Maximize/kéo giãn (không chỉ mỗi khung to ra mà chữ/ảnh vẫn tí
        # hin). Debounce qua after() để lúc đang kéo giãn tay không vẽ lại
        # liên tục (kéo giãn tay có thể bắn hàng chục sự kiện Configure).
        self._data_tab_resize_after_id = None
        tree_frame.bind("<Configure>", self._on_data_tab_resize)

        self.data_records = {}  # record key -> record, editable copy for tab Data
        self.data_answer_map = {}  # tree item id -> (record key, answer index)
        self.data_question_map = {}  # record key -> top-level tree item id
        self.data_selected = set()  # record keys ticked for deletion
        self.data_dirty = False  # True while there are unsaved checkbox edits
        self.data_thumbnails = {}  # (image_hash, size) -> PhotoImage (kept alive for Treeview)
        self.data_thumbnail_size = self.DATA_TREE_BASE_THUMB
        self.data_tab_scale = 1.0

        # --- Tab "Test": cấu hình + capture điểm ---
        row = 0
        ttk.Label(test_tab, text="Monitor:").grid(row=row, column=0, sticky="w")
        self.monitor_box = ttk.Combobox(
            test_tab, values=[str(m) for m in self.monitors], state="readonly", width=42
        )
        self.monitor_box.current(default_index)
        self.monitor_box.grid(row=row, column=1, columnspan=2, sticky="we", pady=2)

        row += 1
        ttk.Label(test_tab, text="Delay giữa các góc (s):").grid(
            row=row, column=0, sticky="w"
        )
        self.delay_var = tk.StringVar(value="0.5")
        ttk.Entry(test_tab, textvariable=self.delay_var, width=10).grid(
            row=row, column=1, sticky="w"
        )

        row += 1
        ttk.Label(test_tab, text="Thời gian di chuyển (s):").grid(
            row=row, column=0, sticky="w"
        )
        self.duration_var = tk.StringVar(value="0.5")
        ttk.Entry(test_tab, textvariable=self.duration_var, width=10).grid(
            row=row, column=1, sticky="w"
        )

        row += 1
        ttk.Label(test_tab, text="Margin (px):").grid(row=row, column=0, sticky="w")
        self.margin_var = tk.StringVar(value="5")
        ttk.Entry(test_tab, textvariable=self.margin_var, width=10).grid(
            row=row, column=1, sticky="w"
        )

        row += 1
        ttk.Label(test_tab, text="Số vòng lặp (0 = vô hạn):").grid(
            row=row, column=0, sticky="w"
        )
        self.loops_var = tk.StringVar(value="1")
        ttk.Entry(test_tab, textvariable=self.loops_var, width=10).grid(
            row=row, column=1, sticky="w"
        )

        row += 1
        ttk.Separator(test_tab, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="we", pady=(10, 6)
        )

        row += 1
        ttk.Label(test_tab, text="Điểm tùy chỉnh:").grid(row=row, column=0, sticky="w")
        capture_btns = ttk.Frame(test_tab)
        capture_btns.grid(row=row, column=1, columnspan=2, sticky="w")
        self.capture_btn = ttk.Button(
            capture_btns, text="Capture điểm", command=self.toggle_capture
        )
        self.capture_btn.grid(row=0, column=0, padx=(0, 4))
        self.clear_capture_btn = ttk.Button(
            capture_btns, text="Xóa điểm", command=self.clear_captured_points
        )
        self.clear_capture_btn.grid(row=0, column=1)

        row += 1
        self.captured_count_var = tk.StringVar(value="Đã capture: 0 điểm.")
        ttk.Label(
            test_tab, textvariable=self.captured_count_var, foreground="#555"
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 0))

        row += 1
        ttk.Label(test_tab, text="Chế độ chạy:").grid(
            row=row, column=0, sticky="w", pady=(4, 0)
        )
        self.point_mode_var = tk.StringVar(value="corners")
        mode_frame = ttk.Frame(test_tab)
        mode_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Radiobutton(
            mode_frame,
            text="4 góc màn hình",
            variable=self.point_mode_var,
            value="corners",
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Điểm đã capture",
            variable=self.point_mode_var,
            value="captured",
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        row += 1
        ttk.Separator(test_tab, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="we", pady=(10, 6)
        )

        row += 1
        ttk.Label(test_tab, text="Macro di chuyển chuột:").grid(
            row=row, column=0, columnspan=3, sticky="w"
        )

        row += 1
        mouse_macro_btns = ttk.Frame(test_tab)
        mouse_macro_btns.grid(row=row, column=0, columnspan=3, pady=(6, 0))
        self.mouse_start_btn = ttk.Button(
            mouse_macro_btns, text="Start", command=self.start_mouse_macro
        )
        self.mouse_start_btn.grid(row=0, column=0, padx=4)
        self.mouse_stop_btn = ttk.Button(
            mouse_macro_btns,
            text="Stop",
            command=self.stop_mouse_macro,
            state="disabled",
        )
        self.mouse_stop_btn.grid(row=0, column=1, padx=4)

        row += 1
        self.mouse_status_var = tk.StringVar(value="Sẵn sàng.")
        ttk.Label(test_tab, textvariable=self.mouse_status_var, foreground="#555").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        # Notebook (các tab) giãn to ra khi phóng to cửa sổ (Maximize).
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Phím tắt toàn cục (không cần cửa sổ app đang được focus) để khỏi
        # phải click vào app rồi làm mất focus tab trình duyệt — nhiều trang
        # thi có chống gian lận, phát hiện rời màn hình khi đổi cửa sổ.
        self.hotkey_listener = pynput_keyboard.GlobalHotKeys(
            {
                "<ctrl>+<shift>+s": self.on_start_hotkey,
                "<ctrl>+<shift>+e": self.on_stop_hotkey,
                "<ctrl>+<shift>+q": self.on_detect_one_hotkey,
            }
        )
        self.hotkey_listener.start()

        notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        self.refresh_data_tab()

        # Log giờ chỉ hiện qua cửa sổ nổi riêng (không còn khung Log trong
        # app) - hiện sẵn ngay từ lúc mở app, luôn nổi trên cùng mọi lúc chứ
        # không chỉ khi Start (Ctrl+Shift+S) nữa.
        self.show_log_overlay(self.monitors[self.monitor_box.current()])

    def on_tab_changed(self, event=None):
        if self.notebook.nametowidget(self.notebook.select()) is not self.data_tab:
            return
        if self.data_dirty:
            return  # tránh xóa mất các ô check chưa Lưu
        self.refresh_data_tab()

    def refresh_data_tab(self):
        """Full reload from disk. Discards any unsaved checkbox edits."""
        self.data_records = self.load_ocr_records()
        self.data_selected = set()
        self.data_dirty = False
        self._redraw_data_tree()

    def _redraw_data_tree(self):
        """Vẽ lại Treeview từ self.data_records hiện có trong bộ nhớ - KHÔNG
        đọc lại từ disk, KHÔNG đụng data_selected/data_dirty. Dùng khi chỉ
        cần cập nhật giao diện (vd đổi cỡ chữ/ảnh khi phóng to cửa sổ) mà
        không được làm mất các tick chọn/sửa chưa Lưu."""
        self.data_answer_map = {}
        self.data_question_map = {}
        self.data_tree.delete(*self.data_tree.get_children())
        # Đánh số #1..#n theo đúng thứ tự đang có trong self.data_records -
        # tự động cập nhật lại mỗi khi vẽ lại (vd sau khi Xóa câu hỏi), không
        # cần lưu số này riêng ở đâu cả.
        for index, (key, record) in enumerate(self.data_records.items(), start=1):
            self._insert_data_tab_record(key, record, index)
        self.data_count_var.set(f"{len(self.data_records)} câu hỏi.")

    def _on_data_tab_resize(self, event):
        if self._data_tab_resize_after_id is not None:
            self.root.after_cancel(self._data_tab_resize_after_id)
        # Debounce: chỉ vẽ lại sau khi ngừng kéo giãn ~200ms, tránh vẽ lại
        # liên tục (tốn công, giật) trong lúc đang kéo tay.
        self._data_tab_resize_after_id = self.root.after(200, self._apply_data_tab_scale)

    def _apply_data_tab_scale(self):
        self._data_tab_resize_after_id = None
        width = self.data_tree.winfo_width()
        if width <= 1:
            return
        scale = max(1.0, min(width / self.DATA_TREE_BASE_WIDTH, self.DATA_TREE_MAX_SCALE))
        if abs(scale - self.data_tab_scale) < 0.05:
            return  # thay đổi không đáng kể, khỏi vẽ lại tốn công
        self.data_tab_scale = scale

        font_size = round(self.DATA_TREE_BASE_FONT_SIZE * scale)
        row_height = round(self.DATA_TREE_BASE_ROWHEIGHT * scale)
        indicator_size = round(self.DATA_TREE_BASE_INDICATOR * scale)
        self.data_thumbnail_size = round(self.DATA_TREE_BASE_THUMB * scale)

        self.data_tree_style.configure(
            "Data.Treeview",
            rowheight=row_height,
            font=("TkDefaultFont", font_size),
            indicatorsize=indicator_size,
        )
        self.data_tree.tag_configure(
            "question", font=("TkDefaultFont", font_size, "bold")
        )
        self.data_tree.tag_configure("answer", font=("TkDefaultFont", font_size))
        self.data_tree.column("#0", width=round(self.DATA_TREE_BASE_WIDTH * scale))
        self._redraw_data_tree()

    def add_data_tab_record(self, record):
        """Append/replace a single question live (called while Detect is
        running) without touching other rows' pending checkbox edits."""
        key = self._record_key(record["question"], record.get("image_hash"))
        old_qid = self.data_question_map.get(key)
        if old_qid is not None and self.data_tree.exists(old_qid):
            for child in self.data_tree.get_children(old_qid):
                self.data_answer_map.pop(child, None)
            self.data_tree.delete(old_qid)

        self.data_records[key] = record
        index = list(self.data_records.keys()).index(key) + 1
        self._insert_data_tab_record(key, record, index)
        self.data_count_var.set(f"{len(self.data_records)} câu hỏi.")

    def _insert_data_tab_record(self, key, record, index):
        qid = self.data_tree.insert(
            "",
            "end",
            text=self._question_display_text(key, record, index),
            image=self._get_thumbnail(record.get("image_hash")),
            tags=("question",),
        )
        self.data_question_map[key] = qid
        for a_index, answer in enumerate(record.get("answers", [])):
            item_id = self.data_tree.insert(
                qid, "end", text=self._answer_display_text(answer), tags=("answer",)
            )
            self.data_answer_map[item_id] = (key, a_index)

    def _get_thumbnail(self, image_hash):
        """Return a PhotoImage (sized theo self.data_thumbnail_size, tăng
        theo tỉ lệ phóng to cửa sổ) for the Treeview row icon, or "" if this
        record has no image (or the cached PNG can't be loaded)."""
        if not image_hash:
            return ""
        cache_key = (image_hash, self.data_thumbnail_size)
        cached = self.data_thumbnails.get(cache_key)
        if cached is not None:
            return cached
        path = QUESTION_IMAGES_DIR / f"{image_hash}.png"
        if not path.exists():
            return ""
        try:
            img = Image.open(path)
            img.thumbnail((self.data_thumbnail_size, self.data_thumbnail_size))
            photo = ImageTk.PhotoImage(img)
        except Exception:
            return ""
        self.data_thumbnails[cache_key] = photo
        return photo

    def _question_display_text(self, key, record, index):
        checkbox = "☑" if key in self.data_selected else "☐"
        suffix = " [ảnh]" if record.get("image_hash") else ""
        return f"{checkbox} #{index} {record.get('question', '')}{suffix}"

    @staticmethod
    def _answer_display_text(answer):
        checkbox = "☑" if answer.get("is_correct") else "☐"
        return f"{checkbox} {answer.get('index', '?')}. {answer.get('text', '')}"

    def on_data_tree_click(self, event):
        # Bấm vào dấu +/- (thu/mở rộng câu hỏi) không được tính là tick chọn
        # checkbox - để mặc định Treeview tự xử lý việc mở/đóng, chỉ toggle
        # checkbox khi bấm đúng vào phần chữ/ảnh của dòng.
        if self.data_tree.identify_element(event.x, event.y).endswith("indicator"):
            return
        if self.data_tree.identify("region", event.x, event.y) != "tree":
            return
        item_id = self.data_tree.identify_row(event.y)
        if not item_id:
            return

        answer_mapping = self.data_answer_map.get(item_id)
        if answer_mapping is not None:
            key, a_index = answer_mapping
            answer = self.data_records[key]["answers"][a_index]
            answer["is_correct"] = not answer.get("is_correct", False)
            self.data_tree.item(item_id, text=self._answer_display_text(answer))
            self.data_dirty = True
            return

        # not an answer row: must be a question row -> toggle "chọn để xóa"
        key = next(
            (k for k, qid in self.data_question_map.items() if qid == item_id), None
        )
        if key is None:
            return
        if key in self.data_selected:
            self.data_selected.discard(key)
        else:
            self.data_selected.add(key)
        index = list(self.data_records.keys()).index(key) + 1
        self.data_tree.item(
            item_id, text=self._question_display_text(key, self.data_records[key], index)
        )

    def _write_data_records_to_disk(self, records):
        try:
            with open(OCR_RECORDS_PATH, "w", encoding="utf-8") as f:
                json.dump(list(records.values()), f, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            self.log(f"Lỗi ghi {OCR_RECORDS_PATH.name}: {exc}")
            return False

    def save_data_records(self):
        if not self._write_data_records_to_disk(self.data_records):
            return
        # keep the running OCR session's copy in sync, so a later duplicate
        # detection doesn't overwrite the đúng/sai marks you just saved
        self.ocr_records.update(self.data_records)
        self.data_dirty = False
        self.log(f"Đã lưu {len(self.data_records)} câu hỏi vào {OCR_RECORDS_PATH.name}.")

    def _cleanup_question_images(self, removed_records, remaining_records):
        """Xóa file ảnh minh họa (question_images/<hash>.png) của các câu hỏi
        đã bị xóa - trừ khi hash ảnh đó vẫn còn được câu hỏi khác dùng chung
        (image-variant: cùng câu hỏi/đáp án nhưng khác hình)."""
        remaining_hashes = {
            r.get("image_hash") for r in remaining_records.values() if r.get("image_hash")
        }
        removed_hashes = {
            r.get("image_hash") for r in removed_records if r.get("image_hash")
        }
        for image_hash in removed_hashes - remaining_hashes:
            path = QUESTION_IMAGES_DIR / f"{image_hash}.png"
            try:
                if path.exists():
                    path.unlink()
            except Exception as exc:
                self.log(f"Lỗi xóa ảnh {path.name}: {exc}")

    # Ngưỡng "giống nhau" khi so câu hỏi/đáp án cho việc lọc trùng lặp: 1.0
    # là khớp tuyệt đối, thấp hơn cho phép sai khác nhỏ do OCR đọc lệch vài
    # ký tự/dấu giữa 2 lần detect cùng 1 câu hỏi thật ngoài đời.
    DUPLICATE_TEXT_SIMILARITY = 0.92

    @staticmethod
    def _text_similar(text_a, text_b):
        norm_a = normalize_for_match(text_a or "")
        norm_b = normalize_for_match(text_b or "")
        if norm_a == norm_b:
            return True
        ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
        return ratio >= App.DUPLICATE_TEXT_SIMILARITY

    def _images_look_same(self, hash_a, hash_b):
        if not hash_a and not hash_b:
            return True
        if not hash_a or not hash_b:
            return False
        if hash_a == hash_b:
            return True
        try:
            dist = imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
            return dist <= self.IMAGE_HASH_MATCH_THRESHOLD
        except Exception:
            return False

    def _records_look_duplicate(self, rec_a, rec_b):
        """Coi là trùng lặp khi CẢ BA: ảnh giống nhau (hoặc cả hai đều không
        có ảnh) + câu hỏi giống nhau + bộ đáp án (không phân biệt thứ tự)
        giống nhau."""
        if not self._images_look_same(rec_a.get("image_hash"), rec_b.get("image_hash")):
            return False
        if not self._text_similar(rec_a.get("question"), rec_b.get("question")):
            return False

        answers_a = sorted(
            (a.get("text", "") for a in rec_a.get("answers", [])),
            key=normalize_for_match,
        )
        answers_b = sorted(
            (a.get("text", "") for a in rec_b.get("answers", [])),
            key=normalize_for_match,
        )
        if len(answers_a) != len(answers_b):
            return False
        return all(self._text_similar(ta, tb) for ta, tb in zip(answers_a, answers_b))

    def find_duplicate_questions(self):
        """Trả về list các cặp (index_i, index_j, key_i, key_j) - đánh số
        #1..#n theo đúng thứ tự hiện có trong self.data_records, giống hệt số
        thứ tự đang hiển thị trong tab Data."""
        items = list(enumerate(self.data_records.items(), start=1))
        duplicates = []
        for a in range(len(items)):
            idx_i, (key_i, rec_i) = items[a]
            for b in range(a + 1, len(items)):
                idx_j, (key_j, rec_j) = items[b]
                if self._records_look_duplicate(rec_i, rec_j):
                    duplicates.append((idx_i, idx_j, key_i, key_j))
        return duplicates

    def check_duplicate_questions(self):
        """Nút "Lọc trùng lặp" (tab App): đối chiếu TOÀN BỘ câu hỏi đã lưu,
        cảnh báo các cặp câu hỏi (+ ảnh + đáp án) trùng/gần trùng nhau, tham
        chiếu theo số thứ tự #1..#n (số này tự cập nhật mỗi khi xóa câu hỏi
        vì luôn tính lại theo thứ tự hiện có, không lưu cố định)."""
        self.refresh_data_tab()  # đồng bộ với đúng dữ liệu đã lưu trên đĩa
        duplicates = self.find_duplicate_questions()

        if not duplicates:
            self.log("[Lọc] Không phát hiện câu hỏi/ảnh/đáp án nào trùng lặp.")
            messagebox.showinfo(
                "Lọc trùng lặp", "Không phát hiện câu hỏi nào bị trùng lặp."
            )
            return

        lines = [f"#{i} trùng với #{j}" for i, j, _key_i, _key_j in duplicates]
        self.log(
            f"[Lọc] Phát hiện {len(duplicates)} cặp câu hỏi trùng lặp:\n    - "
            + "\n    - ".join(lines)
        )
        messagebox.showwarning(
            "Phát hiện trùng lặp",
            f"Tìm thấy {len(duplicates)} cặp câu hỏi có thể trùng lặp "
            "(cùng ảnh + câu hỏi + đáp án):\n\n" + "\n".join(lines),
        )

    def delete_selected_data_records(self):
        if not self.data_selected:
            self.log("Chưa chọn câu hỏi để xóa.")
            return

        count = len(self.data_selected)
        removed_records = []
        for key in self.data_selected:
            record = self.data_records.pop(key, None)
            if record is not None:
                removed_records.append(record)
            self.ocr_records.pop(key, None)

        if not self._write_data_records_to_disk(self.data_records):
            return
        self._cleanup_question_images(removed_records, self.data_records)
        self.log(f"Đã xóa {count} câu hỏi khỏi {OCR_RECORDS_PATH.name}.")
        self.refresh_data_tab()

    def delete_all_data_records(self):
        if not self.data_records:
            self.log("Không có dữ liệu để xóa.")
            return
        if not messagebox.askyesno(
            "Xác nhận xóa toàn bộ",
            f"Xóa TOÀN BỘ {len(self.data_records)} câu hỏi trong {OCR_RECORDS_PATH.name}?\n"
            "Hành động này không thể hoàn tác.",
        ):
            return

        removed_records = list(self.data_records.values())
        self.ocr_records.clear()
        if not self._write_data_records_to_disk({}):
            return
        self._cleanup_question_images(removed_records, {})
        self.log(f"Đã xóa toàn bộ dữ liệu trong {OCR_RECORDS_PATH.name}.")
        self.refresh_data_tab()

    def on_start_hotkey(self):
        """Chạy trên thread của pynput GlobalHotKeys -> phải chuyển vào
        main thread trước khi đụng tới widget Tkinter."""
        self.root.after(0, self.on_start_shortcut)

    def on_stop_hotkey(self):
        self.root.after(0, self.on_stop_shortcut)

    def on_detect_one_hotkey(self):
        self.root.after(0, self.trigger_detect_one)

    def trigger_detect_one(self):
        """Ctrl+Shift+Q: detect đúng 1 câu hỏi đang hiện trên màn hình rồi
        dừng ngay (đây là cách DUY NHẤT để quét - Start chỉ khởi động, không
        tự quét), ghi luôn vào json bất kể đã có sẵn y hệt hay chưa (không so
        sánh trùng lặp) - bấm lại để detect câu tiếp theo."""
        if not self.detect_armed:
            self.log("Chưa Start (Ctrl+Shift+S) - bấm Start trước khi Detect 1 câu.")
            return
        if self._detect_one_busy:
            self.log("Đang detect 1 câu, đợi xong rồi bấm lại.")
            return

        monitor = self.monitors[self.monitor_box.current()]
        self._detect_one_busy = True
        self.log(f"[Detect 1 câu] Đang quét trên {monitor.name}...")

        threading.Thread(
            target=self.detect_one_worker, args=(monitor,), daemon=True
        ).start()

    def detect_one_worker(self, monitor):
        try:
            try:
                reader = self.get_ocr_reader()
            except Exception as exc:
                self.log(f"Lỗi khởi tạo OCR: {exc}")
                return

            bbox = (
                monitor.x,
                monitor.y,
                monitor.x + monitor.width,
                monitor.y + monitor.height,
            )
            try:
                image = ImageGrab.grab(bbox=bbox)
                results = self.ocr_read(reader, image)
            except Exception as exc:
                self.log(f"Lỗi khi chụp/OCR màn hình: {exc}")
                return

            blocks = self.find_question_blocks(results)
            if not blocks:
                # Log kèm TOÀN BỘ các dòng OCR đọc được (chụp cả màn hình nên
                # có thể rất nhiều dòng: tab trình duyệt, bookmark, menu
                # khóa học... nằm phía TRÊN header câu hỏi thật) để biết ngay
                # vì sao không khớp mẫu header/đáp án, thay vì chỉ báo chung
                # chung không biết đường nào mà sửa. Giới hạn 120 dòng để
                # tránh làm tràn log nếu OCR đọc quá nhiều rác.
                limit = 120
                preview = "\n".join(f"    - {t}" for _b, t in results[:limit])
                extra = (
                    f"\n    ... và {len(results) - limit} dòng nữa (đã cắt bớt)"
                    if len(results) > limit
                    else ""
                )
                self.log(
                    "[Detect 1 câu] Không tìm thấy câu hỏi nào trên màn hình.\n"
                    f"Tổng {len(results)} dòng OCR đọc được:\n"
                    + (preview or "    (không đọc được dòng nào)")
                    + extra
                )
                return

            block = blocks[0]  # chỉ lấy 1 câu hỏi đầu tiên tìm thấy
            q_text = block["question_text"]
            answer_items = block["answers"]

            image_crop = self.extract_question_image(image, block)
            image_hash = (
                self.compute_image_hash(image_crop)
                if image_crop is not None
                else None
            )
            if image_crop is not None and image_hash is not None:
                self.save_question_image_file(image_crop, image_hash)

            key = self.resolve_record_key(
                q_text, image_hash, create_new_if_unmatched=True
            )
            record = {
                "question": q_text,
                "image_hash": image_hash,
                "question_position": self.box_to_rect(
                    block["question_box"], monitor.x, monitor.y
                ),
                "answers": [
                    {
                        "index": i + 1,
                        "text": a_text,
                        "position": self.box_to_rect(a_box, monitor.x, monitor.y),
                        "is_correct": False,
                    }
                    for i, (a_box, a_text) in enumerate(answer_items)
                ],
            }
            self.ocr_records[key] = record
            self.save_ocr_records()
            self.root.after(0, self.add_data_tab_record, record)

            image_note = " [có ảnh]" if image_hash else ""
            log_text = "\n".join(
                [q_text + image_note]
                + [f"    - {a['text']}" for a in record["answers"]]
            )
            self.log(f"[Detect 1 câu] {log_text}")
        finally:
            self._detect_one_busy = False

    def on_start_shortcut(self, event=None):
        if str(self.start_btn["state"]) == "disabled":
            return
        self.start_detect_and_record()

    def on_stop_shortcut(self, event=None):
        if str(self.stop_btn["state"]) == "disabled":
            return
        self.stop_detect_and_record()

    def toggle_capture(self):
        if self.capturing:
            self.stop_capture()
        else:
            self.start_capture()

    def start_capture(self):
        self.capturing = True
        self.capture_btn.config(text="Dừng capture (Esc)")
        self.mouse_start_btn.config(state="disabled")
        self.log(
            "Bắt đầu capture điểm. Click vào các vị trí trên màn hình, nhấn Esc để dừng."
        )

        self.mouse_listener = pynput_mouse.Listener(on_click=self.on_mouse_click)
        self.mouse_listener.start()
        self.keyboard_listener = pynput_keyboard.Listener(on_press=self.on_key_press)
        self.keyboard_listener.start()

    def stop_capture(self):
        if not self.capturing:
            return
        self.capturing = False
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
        self.capture_btn.config(text="Capture điểm")
        self.mouse_start_btn.config(state="normal")
        self.log(f"Đã dừng capture. Tổng cộng {len(self.captured_points)} điểm.")

    def on_mouse_click(self, x, y, button, pressed):
        """Runs on the pynput listener thread; only left-click presses outside
        the app window are recorded, so clicking our own buttons is ignored."""
        if not pressed or button != pynput_mouse.Button.left:
            return
        if self.is_inside_window(x, y):
            return
        self.root.after(0, self.add_captured_point, x, y)

    def on_key_press(self, key):
        """Runs on the pynput listener thread."""
        if key == pynput_keyboard.Key.esc:
            self.root.after(0, self.stop_capture)
            return False  # stop this keyboard listener
        return None

    def is_inside_window(self, x, y):
        wx = self.root.winfo_rootx()
        wy = self.root.winfo_rooty()
        ww = self.root.winfo_width()
        wh = self.root.winfo_height()
        return wx <= x <= wx + ww and wy <= y <= wy + wh

    def add_captured_point(self, x, y):
        self.captured_points.append((x, y))
        self.captured_count_var.set(f"Đã capture: {len(self.captured_points)} điểm.")
        self.log(f"Đã capture điểm ({x}, {y}).")

    def clear_captured_points(self):
        self.stop_capture()
        count = len(self.captured_points)
        self.captured_points.clear()
        self.captured_count_var.set("Đã capture: 0 điểm.")
        self.log(f"Đã xóa {count} điểm.")

    def start_mouse_macro(self):
        try:
            delay = float(self.delay_var.get())
            duration = float(self.duration_var.get())
            margin = int(self.margin_var.get())
            loops = int(self.loops_var.get())
        except ValueError:
            self.mouse_status_var.set("Giá trị nhập không hợp lệ.")
            self.log("Giá trị nhập không hợp lệ.")
            return

        if self.point_mode_var.get() == "captured":
            if not self.captured_points:
                self.mouse_status_var.set("Chưa có điểm nào được capture.")
                self.log("Chưa có điểm nào được capture.")
                return
            points = list(self.captured_points)
            target_desc = f"{len(points)} điểm đã capture"
        else:
            monitor = self.monitors[self.monitor_box.current()]
            points = core.corners_of(monitor, margin)
            target_desc = monitor.name

        self.log(
            f"Bắt đầu macro chuột trên {target_desc} (delay={delay}s, duration={duration}s, loops={loops})."
        )
        self.stop_event.clear()
        self.mouse_start_btn.config(state="disabled")
        self.mouse_stop_btn.config(state="normal")
        self.monitor_box.config(state="disabled")
        self.capture_btn.config(state="disabled")

        self.worker = threading.Thread(
            target=self.run_mouse_macro,
            args=(points, target_desc, loops, delay, duration),
            daemon=True,
        )
        self.worker.start()

    def stop_mouse_macro(self):
        self.stop_event.set()
        self.mouse_status_var.set("Đang dừng...")
        self.log("Đang dừng macro chuột...")

    def start_tool(self):
        try:
            interval = float(self.tool_interval_var.get())
            if interval <= 0:
                raise ValueError
        except ValueError:
            self.tool_status_var.set("Chu kỳ quét không hợp lệ.")
            self.log("Chu kỳ quét Tool không hợp lệ.")
            return

        try:
            offset = int(self.tool_offset_var.get())
        except ValueError:
            self.tool_status_var.set("Khoảng cách lề không hợp lệ.")
            self.log("Khoảng cách lề đáp án (Tool) không hợp lệ.")
            return

        monitor = self.monitors[self.monitor_box.current()]
        self.ocr_records = self.load_ocr_records()
        self.tool_stop_event.clear()
        self.tool_start_btn.config(state="disabled")
        self.tool_stop_btn.config(state="normal")
        self.tool_status_var.set("Đang chạy...")
        self.log(
            f"Bắt đầu Tool (đối chiếu đáp án đúng + click) trên {monitor.name}, "
            f"chu kỳ {interval}s."
        )

        self.tool_thread = threading.Thread(
            target=self.tool_worker, args=(monitor, interval, offset), daemon=True
        )
        self.tool_thread.start()

    def stop_tool(self):
        self.tool_stop_event.set()
        self.tool_status_var.set("Đang dừng...")
        self.log("Đang dừng Tool...")

    def tool_worker(self, monitor, interval, offset):
        try:
            reader = self.get_ocr_reader()
        except Exception as exc:
            self.log(f"Lỗi khởi tạo OCR: {exc}")
            self.root.after(0, self.on_tool_finished)
            return

        bbox = (
            monitor.x,
            monitor.y,
            monitor.x + monitor.width,
            monitor.y + monitor.height,
        )
        answered = set()  # record key (câu hỏi + hash ảnh) đã click trong phiên Tool này
        self._last_tool_frame_sig = None
        try:
            while not self.tool_stop_event.is_set():
                try:
                    image = ImageGrab.grab(bbox=bbox)
                except Exception as exc:
                    self.log(f"Lỗi khi chụp màn hình: {exc}")
                    if self.wait_tool_cancelable(interval):
                        break
                    continue

                frame_sig = self._frame_signature(image)
                if frame_sig is not None and frame_sig == self._last_tool_frame_sig:
                    # Màn hình chưa đổi so với lần quét trước -> khỏi OCR lại.
                    if self.wait_tool_cancelable(interval):
                        break
                    continue
                self._last_tool_frame_sig = frame_sig

                try:
                    results = self.ocr_read(reader, image)
                except Exception as exc:
                    self.log(f"Lỗi khi OCR màn hình: {exc}")
                    results = []

                for block in self.find_question_blocks(results):
                    q_text = block["question_text"]
                    answer_items = block["answers"]

                    image_crop = self.extract_question_image(image, block)
                    image_hash = (
                        self.compute_image_hash(image_crop)
                        if image_crop is not None
                        else None
                    )
                    saved_key = self.resolve_record_key(q_text, image_hash)
                    if saved_key is None:
                        continue  # chưa có trong dữ liệu đã lưu
                    if saved_key in answered:
                        continue
                    saved = self.ocr_records[saved_key]

                    correct_texts = {
                        a["text"] for a in saved.get("answers", []) if a.get("is_correct")
                    }
                    if not correct_texts:
                        continue  # chưa đối chiếu được đáp án đúng, bỏ qua

                    match = next(
                        (
                            (a_box, a_text)
                            for a_box, a_text in answer_items
                            if a_text in correct_texts
                        ),
                        None,
                    )
                    if match is None:
                        continue

                    a_box, a_text = match
                    rect = self.box_to_rect(a_box, monitor.x, monitor.y)
                    click_x = rect["x"] - offset
                    click_y = rect["y"] + rect["height"] // 2

                    try:
                        pyautogui.moveTo(click_x, click_y, duration=0.2)
                        pyautogui.click()
                        answered.add(saved_key)
                        self.log(
                            f"[TOOL] Click đáp án đúng cho '{q_text}': '{a_text}' "
                            f"tại ({click_x}, {click_y})."
                        )
                    except pyautogui.FailSafeException:
                        self.log("Tool dừng khẩn cấp (chuột chạm góc 0,0).")
                        self.tool_stop_event.set()
                        break

                if self.wait_tool_cancelable(interval):
                    break
        finally:
            self.log("Đã dừng Tool.")
            self.root.after(0, self.on_tool_finished)

    def wait_tool_cancelable(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.tool_stop_event.is_set():
                return True
            time.sleep(min(0.05, max(0.0, end - time.time())))
        return False

    def on_tool_finished(self):
        self.tool_start_btn.config(state="normal")
        self.tool_stop_btn.config(state="disabled")
        self.tool_status_var.set("Sẵn sàng.")

    def start_detect_and_record(self):
        """Chỉ "khởi động": nạp sẵn model OCR (bước chậm nhất), KHÔNG tự quét
        màn hình. Quét thực sự chỉ diễn ra khi bấm Ctrl+Shift+Q
        (trigger_detect_one), mỗi lần đúng 1 câu."""
        monitor = self.monitors[self.monitor_box.current()]
        self.ocr_records = self.load_ocr_records()
        self.detect_armed = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("Đã khởi động - Ctrl+Shift+Q để detect 1 câu.")
        self.log(
            f"Đã khởi động trên {monitor.name} (chưa quét). Bấm Ctrl+Shift+Q để "
            f"detect từng câu (file: {OCR_RECORDS_PATH.name})."
        )
        threading.Thread(target=self._preload_ocr_reader, daemon=True).start()

    def _preload_ocr_reader(self):
        try:
            self.get_ocr_reader()
        except Exception as exc:
            self.log(f"Lỗi khởi tạo OCR: {exc}")

    def stop_detect_and_record(self):
        self.detect_armed = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("Sẵn sàng.")
        self.log("Đã dừng.")

    @staticmethod
    def _gpu_available():
        # easyocr kéo theo torch nên import này luôn sẵn có. Dùng GPU (nếu
        # máy có card NVIDIA + CUDA) nhanh hơn CPU rất nhiều lần cho cùng
        # một ảnh, không đánh đổi độ chính xác.
        try:
            import torch

            return torch.cuda.is_available()
        except Exception:
            return False

    def get_ocr_reader(self):
        """Lazily create the easyocr reader (slow: loads/downloads models)."""
        if self.ocr_reader is None:
            use_gpu = self._gpu_available()
            self.log(
                "Đang khởi tạo OCR "
                f"({'GPU' if use_gpu else 'CPU'}, mô hình đã cache sẵn thì rất nhanh)..."
            )
            import easyocr

            self.ocr_reader = easyocr.Reader(["vi", "en"], gpu=use_gpu)
            self.log("OCR sẵn sàng.")
        return self.ocr_reader

    # Phóng to ảnh trước khi đưa vào OCR giúp nhận diện chữ tiếng Việt (dấu,
    # chữ nhỏ) chính xác hơn hẳn. Chỉnh nhỏ lại (vd 1.0) nếu máy yếu, quét
    # chậm; chỉnh lớn hơn nếu vẫn còn đọc sai nhiều mà máy đủ khỏe.
    OCR_UPSCALE_FACTOR = 1.5

    # Số vùng chữ được nhận dạng (bước recognition) cùng lúc trong 1 batch:
    # tận dụng xử lý song song (đặc biệt trên GPU) thay vì lần lượt từng
    # dòng một — nhanh hơn hẳn cho trang có nhiều dòng đáp án, không đổi kết
    # quả nhận dạng (chỉ gộp việc tính toán, không đổi thuật toán).
    OCR_BATCH_SIZE = 8

    def ocr_read(self, reader, pil_image):
        """Chạy OCR trên bản phóng to của pil_image, rồi quy đổi tọa độ các
        box về lại đúng hệ tọa độ gốc (chưa phóng to) và sắp theo thứ tự trên
        xuống — để toàn bộ phần còn lại của pipeline (find_question_blocks,
        extract_question_image, box_to_rect, ...) không cần biết gì về việc
        phóng to này, vẫn thao tác trên tọa độ ảnh chụp màn hình gốc."""
        scale = self.OCR_UPSCALE_FACTOR
        source = pil_image
        if scale != 1:
            source = pil_image.resize(
                (round(pil_image.width * scale), round(pil_image.height * scale)),
                Image.LANCZOS,
            )
        results = reader.readtext(
            np.array(source),
            detail=1,
            paragraph=True,
            batch_size=self.OCR_BATCH_SIZE,
        )
        if scale != 1:
            results = [
                ([[x / scale, y / scale] for x, y in box], text)
                for box, text in results
            ]
        results.sort(key=lambda r: min(point[1] for point in r[0]))
        return results

    # Trang "Kiểm tra" thực tế có tới 3 cột: menu khóa học bên trái, nội dung
    # câu hỏi ở giữa, bảng điều hướng số câu bên phải. Khi gộp toàn màn hình
    # theo thứ tự trên xuống, chữ ở 2 cột kia có thể chen ngang giữa các dòng
    # của cột nội dung (menu bên trái đặc biệt dài, trùng cả khoảng chứa ảnh
    # minh họa). Dòng nào lệch trái/phải quá xa so với header câu hỏi coi như
    # thuộc cột khác, bỏ qua thay vì làm hỏng block. Giữ hệ số nhỏ vì 2 cột
    # kia thường cách xa hàng trăm px, trong khi thụt lề tự nhiên giữa
    # header/câu hỏi/đáp án chỉ lệch vài px tới ~1 dòng.
    COLUMN_LEFT_TOLERANCE_RATIO = 3

    @staticmethod
    def _line_edges(box):
        ys = [point[1] for point in box]
        return min(ys), max(ys)

    @staticmethod
    def _line_left(box):
        return min(point[0] for point in box)

    @staticmethod
    def _line_right(box):
        return max(point[0] for point in box)

    # Ở chế độ paragraph=True, easyocr đôi khi gộp 2-3 dòng đáp án liền kề
    # (khoảng cách dòng gần nhau) vào chung MỘT khối text, ví dụ:
    # "2-Xe cứu thương... 3-Xe con (B)...". Nếu để nguyên, cả khối bị coi là
    # MỘT đáp án duy nhất (sai index, sai nội dung). Tách lại dựa vào các mốc
    # số thứ tự liên tiếp (1-, 2-, 3-, ...) xuất hiện ngay sau khoảng trắng.
    # Lookbehind KHÔNG-tiêu-thụ ký tự (zero-width) thay vì (?:^|\s) tiêu thụ
    # khoảng trắng: nếu dùng \s* tiêu thụ khoảng trắng sau dấu -/. của 1 mốc
    # "giả" (số nằm trong nội dung câu trả lời, vd "5." trong "và 5. 2-..."),
    # khoảng trắng ngăn cách trước mốc THẬT kế tiếp ("2-") sẽ bị nuốt mất,
    # khiến finditer (vốn không overlap) không thể nhận ra mốc đó nữa.
    _MERGED_ANSWER_MARKER_PATTERN = re.compile(r"(?<!\S)(\d{1,2})[-.]")

    @classmethod
    def _split_merged_answer_text(cls, text):
        matches = list(cls._MERGED_ANSWER_MARKER_PATTERN.finditer(text))
        if len(matches) <= 1:
            return [text]
        # Bỏ qua (không phải break) các match không khớp số kỳ vọng tiếp
        # theo: nội dung đáp án có thể tự chứa số trùng dạng "N-"/"N."
        # (vd "1-Hướng 2 và 5. 2-Chỉ hướng 1." có "5." là 1 phần câu, không
        # phải mốc đáp án) - break sớm sẽ bỏ lỡ mốc thật nằm phía sau.
        starts = []
        expected = None
        for m in matches:
            num = int(m.group(1))
            if expected is None:
                starts.append(m.start())
                expected = num + 1
                continue
            if num == expected:
                starts.append(m.start())
                expected += 1
        if len(starts) <= 1:
            return [text]
        boundaries = starts[1:] + [len(text)]
        segments = [
            text[start:end].strip() for start, end in zip(starts, boundaries)
        ]
        return [seg for seg in segments if seg]

    @classmethod
    def _split_question_and_merged_answers(cls, text):
        """Trường hợp cực đoan hơn _split_merged_answer_text: easyocr đôi
        khi gộp LUÔN cả câu hỏi lẫn TOÀN BỘ đáp án vào một dòng duy nhất
        (paragraph mode gộp quá đà), ví dụ:
        "Xe của bạn... trong trường hợp này? 1-Chuyển sang... 2-Dừng lại...
        3-Dừng lại...". Dòng này KHÔNG bắt đầu bằng số thứ tự nên
        ANSWER_OPTION_PATTERN.match() thất bại ngay từ đầu, và vì chưa có
        đáp án nào nên trước đây bị coi nguyên cả dòng là câu hỏi (không có
        đáp án nào được tách ra -> block bị loại bỏ hoàn toàn, "Không tìm
        thấy câu hỏi nào").

        Trả về (question_text_hoặc_None, [answer_text, ...]). Mốc "1-"/"1."
        ĐẦU TIÊN tìm được (không phải mốc bất kỳ) mới được coi là bắt đầu
        đáp án, để tránh nhầm với số ngẫu nhiên xuất hiện trong câu hỏi
        (vd "khoảng cách 2-3m"). Nếu không tìm thấy dãy mốc 1,2,3... hợp lệ,
        trả về ([], text gốc) - coi như không tách được gì, giữ hành vi cũ."""
        matches = list(cls._MERGED_ANSWER_MARKER_PATTERN.finditer(text))
        starts = []
        expected = None
        for m in matches:
            num = int(m.group(1))
            if expected is None:
                if num != 1:
                    continue  # phải bắt đầu đúng từ "1-" mới chắc là đáp án
                starts.append(m.start())
                expected = 2
                continue
            if num == expected:
                starts.append(m.start())
                expected += 1

        if not starts:
            return text, []

        question_part = text[: starts[0]].strip()
        boundaries = starts[1:] + [len(text)]
        answer_segments = [
            text[start:end].strip() for start, end in zip(starts, boundaries)
        ]
        answer_segments = [seg for seg in answer_segments if seg]
        return (question_part or None), answer_segments

    def _split_answer_box(self, box, segment_count):
        # Không có tọa độ dòng chính xác cho từng đáp án con bên trong khối
        # gộp, nên chia đều chiều cao của box gốc theo tỉ lệ số đáp án - đủ
        # gần đúng để Tool tab click vào vùng lân cận đáp án đúng.
        top, bottom = self._line_edges(box)
        left = self._line_left(box)
        right = self._line_right(box)
        height = bottom - top
        step = height / segment_count
        boxes = []
        for i in range(segment_count):
            seg_top = top + step * i
            seg_bottom = top + step * (i + 1)
            boxes.append(
                [
                    [left, seg_top],
                    [right, seg_top],
                    [right, seg_bottom],
                    [left, seg_bottom],
                ]
            )
        return boxes

    def find_question_blocks(self, results):
        """Group OCR results [(box, text), ...] (already in top-to-bottom
        order) into question blocks, matching trang "Kiểm tra" (the
        one-question-at-a-time test page): each question starts at a
        numbered header line like "1. Câu hỏi chọn một đáp án", followed by
        the question sentence (which may sit below an illustration image —
        that vertical gap is irrelevant here since blocks are now driven by
        the text patterns themselves, not geometry), followed by one or more
        numbered answer-option lines like "1-Đúng.". A block ends as soon as
        a line stops matching the answer-option pattern once at least one
        answer has already been collected (a "Kiểm tra"/"Tiếp" button,
        footer text, ...), or when the next question's header appears. Lines
        from the question-number sidebar (a different column) are ignored
        rather than allowed to corrupt or prematurely end the block.

        Returns a list of dicts: {"header_box", "question_box",
        "question_text", "answers": [(box, text), ...], "right_bound"}. The
        header/question boxes (and "right_bound", the left edge of whatever
        got rejected as "a different column, to the right" — a natural hint
        for where the question-navigator sidebar begins) are kept around so
        extract_question_image() can crop the illustration image (if any)
        more accurately than just guessing from text width.
        """
        raw_blocks = []
        current = None  # {"header_box":, "question": [], "answers": [], "right_bound":}
        block_left = None
        for box, text in results:
            text = text.strip()
            if not text:
                continue

            if QUESTION_HEADER_PATTERN.match(normalize_for_match(text)):
                if current is not None and current["answers"]:
                    raw_blocks.append(current)
                current = {
                    "header_box": box,
                    "question": [],
                    "answers": [],
                    "right_bound": None,
                }
                block_left = self._line_left(box)
                continue

            if current is None:
                continue  # dòng lạc trước khi gặp header câu hỏi đầu tiên

            top, bottom = self._line_edges(box)
            height = max(bottom - top, 1)
            left = self._line_left(box)
            if abs(left - block_left) > height * self.COLUMN_LEFT_TOLERANCE_RATIO:
                if left > block_left and not current["answers"]:
                    # Lệch hẳn sang phải, và còn đang trong vùng ảnh/câu hỏi
                    # (chưa có đáp án nào) -> rất có thể là mép trái của cột
                    # điều hướng câu hỏi. Chỉ xét trong giai đoạn này để khỏi
                    # nhầm với các nút bấm footer ("Kiểm tra", "Tiếp") vốn
                    # nằm sau đáp án cuối cùng nhưng vẫn thuộc cùng cột nội
                    # dung, chỉ là lệch tâm/canh phải trong card mà thôi.
                    if current["right_bound"] is None or left < current["right_bound"]:
                        current["right_bound"] = left
                continue  # thuộc cột khác, bỏ qua

            if ANSWER_OPTION_PATTERN.match(text):
                segments = self._split_merged_answer_text(text)
                if len(segments) > 1:
                    sub_boxes = self._split_answer_box(box, len(segments))
                    for sub_box, seg_text in zip(sub_boxes, segments):
                        current["answers"].append((sub_box, seg_text))
                else:
                    current["answers"].append((box, text))
                continue

            if not current["answers"]:
                # Chưa có đáp án nào - dòng này có thể là câu hỏi thuần túy,
                # HOẶC easyocr đã gộp quá đà: cả câu hỏi lẫn toàn bộ đáp án
                # nằm chung 1 dòng (không bắt đầu bằng số thứ tự nên
                # ANSWER_OPTION_PATTERN phía trên không khớp). Thử tách các
                # mốc "1-...2-...3-..." nhúng bên trong trước khi coi nguyên
                # dòng là câu hỏi.
                question_part, answer_segments = self._split_question_and_merged_answers(
                    text
                )
                if answer_segments:
                    if question_part:
                        current["question"].append((box, question_part))
                    sub_boxes = self._split_answer_box(box, len(answer_segments))
                    for sub_box, seg_text in zip(sub_boxes, answer_segments):
                        current["answers"].append((sub_box, seg_text))
                    continue

            if current["answers"]:
                # Đã có đáp án rồi mà dòng này không khớp mẫu đáp án nữa:
                # hết phần của câu hỏi này (nút bấm, footer, ...).
                raw_blocks.append(current)
                current = None
            else:
                current["question"].append((box, text))

        if current is not None and current["answers"]:
            raw_blocks.append(current)

        blocks = []
        for blk in raw_blocks:
            if not blk["question"]:
                continue  # không bắt được câu hỏi (hiếm, bỏ qua cho an toàn)
            blocks.append(
                {
                    "header_box": blk["header_box"],
                    "question_box": blk["question"][0][0],
                    "question_text": " ".join(t for _b, t in blk["question"]),
                    "answers": blk["answers"],
                    "right_bound": blk["right_bound"],
                }
            )
        return blocks

    # Khoảng trống dọc tối thiểu (px) giữa header và câu hỏi để coi là có ảnh
    # minh họa xen giữa (nếu không, chỉ là khoảng cách dòng bình thường).
    MIN_IMAGE_GAP = 40

    # Khoảng cách Hamming tối đa giữa 2 perceptual hash để coi là cùng 1 ảnh.
    IMAGE_HASH_MATCH_THRESHOLD = 6

    def extract_question_image(self, pil_image, block):
        """Crop the illustration image (if any) sitting between the header
        and the question text of `block`. Returns a PIL image, or None if
        this question has no image."""
        header_box = block.get("header_box")
        question_box = block.get("question_box")
        if header_box is None or question_box is None:
            return None

        _h_top, header_bottom = self._line_edges(header_box)
        question_top, _q_bottom = self._line_edges(question_box)
        if question_top - header_bottom < self.MIN_IMAGE_GAP:
            return None

        boxes = [header_box, question_box] + [b for b, _t in block["answers"]]
        left = min(self._line_left(b) for b in boxes)
        text_right = max(self._line_right(b) for b in boxes)

        # Ảnh minh họa thường rộng hơn hẳn dòng chữ dài nhất, nên chỉ dùng độ
        # rộng chữ để cắt sẽ hụt mất 1 phần ảnh bên phải. Nếu biết được mép
        # cột điều hướng câu hỏi (right_bound, thu được lúc gộp block) thì
        # cắt rộng tới sát mép đó; không thì nới thêm 1 khoảng an toàn.
        right_bound = block.get("right_bound")
        if right_bound is not None and right_bound - 12 > text_right:
            right = right_bound - 12
        else:
            right = text_right + 150

        crop_box = (
            max(int(left) - 4, 0),
            int(header_bottom),
            int(right) + 4,
            int(question_top),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            return None
        try:
            return pil_image.crop(crop_box)
        except Exception:
            return None

    @staticmethod
    def compute_image_hash(pil_image):
        try:
            return str(imagehash.average_hash(pil_image))
        except Exception:
            return None

    @staticmethod
    def _frame_signature(pil_image):
        # OCR (đặc biệt với upscale) tốn thời gian gấp nhiều lần so với hash
        # ảnh (average_hash tự resize xuống 8x8 nên rất rẻ dù ảnh gốc to).
        # Giữa các chu kỳ quét, màn hình thường không đổi (người dùng đang
        # đọc câu hỏi) -> bỏ qua hẳn bước OCR khi ảnh chụp giống hệt lần
        # trước, tăng tốc đáng kể mà không ảnh hưởng độ chính xác.
        try:
            return str(imagehash.average_hash(pil_image))
        except Exception:
            return None

    @staticmethod
    def _record_key(question, image_hash):
        return f"{question}␟{image_hash or ''}"

    def save_question_image_file(self, pil_image, image_hash):
        try:
            QUESTION_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            path = QUESTION_IMAGES_DIR / f"{image_hash}.png"
            if not path.exists():
                pil_image.save(path)
        except Exception as exc:
            self.log(f"Lỗi lưu ảnh câu hỏi: {exc}")

    def resolve_record_key(self, q_text, image_hash, create_new_if_unmatched=False):
        """Find which saved record (q_text, image_hash) refers to: first
        match by question text alone to see how many image variants of this
        question are already known, then decide:
        - 0 variants known -> chưa có gì, trả None (hoặc key mới nếu đang ghi).
        - 1 variant known, KHÔNG đang ghi (Tool đối chiếu để click) -> không
          mơ hồ, dùng luôn variant đó, không cần so ảnh chặt (so ảnh ở đây dễ
          trượt ngưỡng vì nhiễu chụp màn hình, không cần thiết cho việc click).
        - 1 variant known, ĐANG ghi (tab App / Detect 1 câu) mà không có ảnh
          hiện tại để so (image_hash rỗng) -> không đủ căn cứ coi là biến thể
          mới, vẫn khớp variant duy nhất đó (tránh tạo bản ghi rác mỗi khi lỡ
          không chụp được ảnh).
        - 1 variant known, ĐANG ghi VÀ có ảnh hiện tại -> PHẢI so hash ảnh
          với variant đã lưu: khớp thì ghi đè đúng variant đó, còn lệch quá
          ngưỡng thì đây là ảnh khác hẳn (câu hỏi trùng nhưng khác hình) -> để
          rơi xuống nhánh tạo key mới bên dưới thay vì ghi đè nhầm lên variant
          cũ (bug trước đây: luôn ghi đè khi chỉ có 1 variant, khiến câu hỏi
          mới với hình khác bị "nuốt mất", coi như không ghi nhận được, đồng
          thời làm lẫn ảnh của câu trước sang câu sau).
        - >=2 variants known -> luôn phải so hash ảnh hiện tại với từng
          variant để biết chính xác đang là ảnh nào, rồi mới suy ra đáp án
          tương ứng.
        `create_new_if_unmatched`: nếu không khớp variant nào (kể cả trường
        hợp 0 variant), trả về 1 key MỚI cho (q_text, image_hash) thay vì
        None — dùng khi đang ghi nhận (tab App), không dùng khi đối chiếu để
        click (tab Tool), vì Tool không được tự bịa ra dữ liệu mới.
        """
        existing_keys = [
            key for key, r in self.ocr_records.items() if r.get("question") == q_text
        ]

        if not existing_keys:
            return self._record_key(q_text, image_hash) if create_new_if_unmatched else None

        if len(existing_keys) == 1 and (not create_new_if_unmatched or not image_hash):
            return existing_keys[0]

        if image_hash:
            try:
                current_hash = imagehash.hex_to_hash(image_hash)
                best_key, best_dist = None, None
                for key in existing_keys:
                    stored_hash = self.ocr_records[key].get("image_hash")
                    if not stored_hash:
                        continue
                    dist = current_hash - imagehash.hex_to_hash(stored_hash)
                    if dist <= self.IMAGE_HASH_MATCH_THRESHOLD and (
                        best_dist is None or dist < best_dist
                    ):
                        best_key, best_dist = key, dist
                if best_key is not None:
                    return best_key
            except Exception:
                pass

        return self._record_key(q_text, image_hash) if create_new_if_unmatched else None

    @staticmethod
    def box_to_rect(box, offset_x, offset_y):
        """Convert an OCR quad (local image coords) to a screen-absolute
        {x, y, width, height} rect, in pixels."""
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        return {
            "x": int(round(min(xs))) + offset_x,
            "y": int(round(min(ys))) + offset_y,
            "width": int(round(max(xs) - min(xs))),
            "height": int(round(max(ys) - min(ys))),
        }

    def load_ocr_records(self):
        if OCR_RECORDS_PATH.exists():
            try:
                with open(OCR_RECORDS_PATH, "r", encoding="utf-8") as f:
                    records = json.load(f)
                return {
                    self._record_key(r["question"], r.get("image_hash")): r
                    for r in records
                }
            except Exception as exc:
                self.log(f"Không đọc được {OCR_RECORDS_PATH.name} cũ: {exc}")
        return {}

    def save_ocr_records(self):
        try:
            with open(OCR_RECORDS_PATH, "w", encoding="utf-8") as f:
                json.dump(list(self.ocr_records.values()), f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.log(f"Lỗi ghi file {OCR_RECORDS_PATH.name}: {exc}")

    def run_mouse_macro(self, points, target_desc, loops, delay, duration):
        self.set_mouse_status(f"Bắt đầu sau 2 giây trên {target_desc}...")
        if self.wait_cancelable(2.0):
            self.set_mouse_status("Đã dừng.")
            self.root.after(0, self.on_mouse_macro_finished)
            return

        count = 0
        try:
            while loops == 0 or count < loops:
                for x, y in points:
                    if self.stop_event.is_set():
                        self.set_mouse_status("Đã dừng.")
                        return
                    pyautogui.moveTo(x, y, duration=duration)
                    if self.wait_cancelable(delay):
                        self.set_mouse_status("Đã dừng.")
                        return
                count += 1
                self.set_mouse_status(
                    f"Đã chạy {count}" + ("" if loops == 0 else f"/{loops}") + " vòng."
                )
            self.set_mouse_status(f"Hoàn tất {count} vòng.")
        except pyautogui.FailSafeException:
            self.set_mouse_status("Đã dừng khẩn cấp (chuột chạm góc 0,0).")
        except Exception as exc:
            self.set_mouse_status(f"Lỗi: {exc}")
        finally:
            self.root.after(0, self.on_mouse_macro_finished)

    def wait_cancelable(self, seconds):
        """Sleep in small steps so Stop reacts quickly. Returns True if canceled."""
        end = time.time() + seconds
        while time.time() < end:
            if self.stop_event.is_set():
                return True
            time.sleep(min(0.05, max(0.0, end - time.time())))
        return False

    def set_mouse_status(self, text):
        self.root.after(0, lambda: self.mouse_status_var.set(text))
        self.log(text)

    def log(self, text):
        timestamp = datetime.now().strftime("%H:%M:%S")

        def append():
            if self.log_overlay_text is None:
                return
            try:
                self.log_overlay_text.config(state="normal")
                self.log_overlay_text.insert("end", f"[{timestamp}] {text}\n")
                self.log_overlay_text.see("end")
                self.log_overlay_text.config(state="disabled")
            except tk.TclError:
                # overlay đã bị đóng (destroy) từ bên ngoài
                self.log_overlay = None
                self.log_overlay_text = None

        self.root.after(0, append)

    LOG_OVERLAY_WIDTH = 420
    LOG_OVERLAY_HEIGHT = 220

    def show_log_overlay(self, monitor):
        """Hiện cửa sổ log nổi ở góc dưới-trái màn hình - đây là nơi DUY
        NHẤT hiển thị log (không còn khung Log trong app), luôn nổi trên
        cùng (topmost) nhưng KHÔNG kích hoạt/cướp focus (dùng WS_EX_NOACTIVATE)
        - để không bị web tính là "rời màn hình" ngay cả khi người dùng đang
        thao tác ở cửa sổ khác."""
        self.hide_log_overlay()

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)

        x = monitor.x + 10
        y = monitor.y + monitor.height - self.LOG_OVERLAY_HEIGHT - 10
        overlay.geometry(f"{self.LOG_OVERLAY_WIDTH}x{self.LOG_OVERLAY_HEIGHT}+{x}+{y}")

        frame = ttk.Frame(overlay, padding=4, relief="solid", borderwidth=1)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Log Detect", font=("Segoe UI", 9, "bold")).pack(
            anchor="w"
        )
        text = scrolledtext.ScrolledText(
            frame, state="disabled", wrap="word", font=("Consolas", 8)
        )
        text.pack(fill="both", expand=True, pady=(2, 0))

        overlay.update_idletasks()
        apply_noactivate_style(overlay.winfo_id())

        self.log_overlay = overlay
        self.log_overlay_text = text

    def hide_log_overlay(self):
        if self.log_overlay is not None:
            try:
                self.log_overlay.destroy()
            except tk.TclError:
                pass
        self.log_overlay = None
        self.log_overlay_text = None

    def on_mouse_macro_finished(self):
        self.mouse_start_btn.config(state="normal")
        self.mouse_stop_btn.config(state="disabled")
        self.monitor_box.config(state="readonly")
        self.capture_btn.config(state="normal")

    def on_close(self):
        self.stop_event.set()
        self.tool_stop_event.set()
        self.stop_capture()
        self.hide_log_overlay()
        if self.hotkey_listener is not None:
            self.hotkey_listener.stop()
        self.root.destroy()


def main():
    try_fix_xwayland_auth()
    root = tk.Tk()
    App(root)
    remove_window_icon(root)
    root.mainloop()


if __name__ == "__main__":
    main()
