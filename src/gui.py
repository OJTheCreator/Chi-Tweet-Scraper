import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from tkinter.scrolledtext import ScrolledText
from src.scraper import (
    CookieExpiredError,
    NetworkError,
    EmptyPagePromptException,
    scrape_tweets,
    scrape_tweet_links_file,
    authenticate,
)
import threading
import asyncio
from datetime import datetime
import os
import sys
from PIL import Image, ImageTk
import webbrowser
from src.state_manager import StateManager
from src.create_cookie import convert_editthiscookie_to_twikit_format


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)


# ========================================
# CLEAN BLUE THEME
# ========================================
class Colors:
    PRIMARY = "#2563eb"  # Main blue
    PRIMARY_DARK = "#1d4ed8"  # Darker blue for hover
    PRIMARY_LIGHT = "#3b82f6"  # Lighter blue
    BG = "#ffffff"  # White background
    BG_SECONDARY = "#f8fafc"  # Very light gray
    BORDER = "#e2e8f0"  # Light border
    TEXT = "#1e293b"  # Dark text
    TEXT_SECONDARY = "#64748b"  # Gray text
    SUCCESS = "#22c55e"  # Green
    ERROR = "#ef4444"  # Red
    WARNING = "#f59e0b"  # Orange


class TweetScraperApp:
    def __init__(self, root):
        self.root = root
        root.title("Chi Tweet Scraper v-1.1.0")
        root.geometry("720x780")
        root.resizable(True, True)
        root.minsize(680, 720)
        root.configure(bg=Colors.BG)

        # Set window icon
        try:
            icon_path = resource_path(os.path.join("assets", "logo.ico"))
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
        except:
            pass

        self.state_manager = StateManager()
        self.paused_for_cookies = False
        self.paused_for_network = False
        self.paused_for_error = False
        self.user_action = None
        # FIX: Track cancellation explicitly instead of relying on task.done()
        self._stop_requested = False
        self._is_running = False
        # FIX: Track current scrape state for better resume
        self.current_scrape_state = {}

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.task = None
        self.loop = None
        self.current_task_type = None
        self.file_path = None
        self.links_file_path = None
        self.save_dir = tk.StringVar(
            value=os.path.join(os.path.dirname(__file__), "..", "data", "exports")
        )

        self.setup_styles()
        self.create_ui()
        self.root.after(500, self.check_for_saved_state)

    def _should_stop(self) -> bool:
        """
        FIX: Unambiguous stop check.
        Only returns True if user explicitly requested stop.
        Does NOT check task.done() which was ambiguous.
        """
        return self._stop_requested

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except:
            pass

        style.configure("TNotebook", background=Colors.BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=Colors.BG_SECONDARY,
            foreground=Colors.TEXT_SECONDARY,
            padding=[20, 8],
            font=("Segoe UI", 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", Colors.BG)],
            foreground=[("selected", Colors.PRIMARY)],
        )
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=4)
        style.configure(
            "TCheckbutton",
            background=Colors.BG,
            foreground=Colors.TEXT,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Blue.Horizontal.TProgressbar",
            background=Colors.PRIMARY,
            troughcolor=Colors.BORDER,
        )
        style.configure("TSpinbox", padding=4)

    def create_ui(self):
        main = tk.Frame(self.root, bg=Colors.BG, padx=20, pady=15)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        self.create_header(main)

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=1, column=0, sticky="nsew", pady=(15, 0))

        self.main_tab = tk.Frame(self.notebook, bg=Colors.BG, padx=15, pady=15)
        self.links_tab = tk.Frame(self.notebook, bg=Colors.BG, padx=15, pady=15)

        self.notebook.add(self.main_tab, text="  Main  ")
        self.notebook.add(self.links_tab, text="  Scrape by Links  ")

        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.rowconfigure(6, weight=1)

        self.links_tab.columnconfigure(0, weight=1)
        self.links_tab.rowconfigure(4, weight=1)

        self.create_main_tab()
        self.create_links_tab()

    def create_header(self, parent):
        header = tk.Frame(parent, bg=Colors.BG)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        logo_frame = tk.Frame(header, bg=Colors.PRIMARY, width=40, height=40)
        logo_frame.grid(row=0, column=0, padx=(0, 12))
        logo_frame.grid_propagate(False)

        # Load logo image with fallback
        self.logo_photo = None
        try:
            logo_path = resource_path(os.path.join("assets", "logo.png"))
            if os.path.exists(logo_path):
                logo_img = Image.open(logo_path)
                logo_img = logo_img.resize((32, 32), Image.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(logo_img)
                tk.Label(logo_frame, image=self.logo_photo, bg=Colors.PRIMARY).place(
                    relx=0.5, rely=0.5, anchor="center"
                )
            else:
                tk.Label(
                    logo_frame,
                    text="CT",
                    font=("Segoe UI", 12, "bold"),
                    bg=Colors.PRIMARY,
                    fg="white",
                ).place(relx=0.5, rely=0.5, anchor="center")
        except Exception:
            tk.Label(
                logo_frame,
                text="CT",
                font=("Segoe UI", 12, "bold"),
                bg=Colors.PRIMARY,
                fg="white",
            ).place(relx=0.5, rely=0.5, anchor="center")

        title_frame = tk.Frame(header, bg=Colors.BG)
        title_frame.grid(row=0, column=1, sticky="w")
        tk.Label(
            title_frame,
            text="Chi Tweet Scraper",
            font=("Segoe UI", 16, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(anchor="w")
        tk.Label(
            title_frame,
            text="Extract tweets reliably",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(anchor="w")

        help_btn = tk.Button(
            header,
            text="Help",
            command=self.show_guide,
            bg=Colors.BG,
            fg=Colors.PRIMARY,
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=10,
        )
        help_btn.grid(row=0, column=2)

    def create_main_tab(self):
        self.create_section_label(self.main_tab, "Configuration", 0)
        config_frame = self.create_card(self.main_tab, 1)
        self.create_config_content(config_frame)

        self.create_section_label(self.main_tab, "Search Parameters", 2)
        search_frame = self.create_card(self.main_tab, 3)
        self.create_search_content(search_frame)

        controls_frame = tk.Frame(self.main_tab, bg=Colors.BG)
        controls_frame.grid(row=4, column=0, sticky="ew", pady=(15, 10))
        self.create_controls(controls_frame)

        self.create_section_label(self.main_tab, "Activity Log", 5)
        log_frame = self.create_card(self.main_tab, 6, expand=True)
        self.create_log(log_frame)

    def create_section_label(self, parent, text, row):
        tk.Label(
            parent,
            text=text,
            font=("Segoe UI", 10, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).grid(row=row, column=0, sticky="w", pady=(10, 5))

    def create_card(self, parent, row, expand=False):
        frame = tk.Frame(
            parent,
            bg=Colors.BG,
            relief="solid",
            bd=1,
            highlightbackground=Colors.BORDER,
            highlightthickness=1,
        )
        frame.grid(row=row, column=0, sticky="nsew" if expand else "ew", pady=(0, 5))
        frame.columnconfigure(0, weight=1)
        if expand:
            parent.rowconfigure(row, weight=1)
            frame.rowconfigure(0, weight=1)
        return frame

    def create_config_content(self, parent):
        inner = tk.Frame(parent, bg=Colors.BG, padx=12, pady=10)
        inner.pack(fill="x")
        inner.columnconfigure(1, weight=1)

        tk.Label(
            inner,
            text="Export format:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).grid(row=0, column=0, sticky="w", pady=4)

        row1 = tk.Frame(inner, bg=Colors.BG)
        row1.grid(row=0, column=1, sticky="ew", pady=4)
        row1.columnconfigure(1, weight=1)

        self.format_var = tk.StringVar(value="Excel")
        fmt_combo = ttk.Combobox(
            row1,
            textvariable=self.format_var,
            values=["Excel", "CSV"],
            state="readonly",
            width=8,
        )
        fmt_combo.grid(row=0, column=0, padx=(0, 10))

        ttk.Entry(row1, textvariable=self.save_dir, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=(0, 5)
        )

        folder_btn = tk.Button(
            row1,
            text="Browse",
            command=self.choose_folder,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 8),
            relief="flat",
            bd=1,
            cursor="hand2",
            padx=8,
            pady=2,
        )
        folder_btn.grid(row=0, column=2)

        row2 = tk.Frame(inner, bg=Colors.BG)
        row2.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 4))

        self.batch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            row2,
            text="Batch mode (multiple usernames from file)",
            variable=self.batch_var,
            command=self.toggle_batch,
        ).pack(side="left")

        self.file_btn = tk.Button(
            row2,
            text="Select File",
            command=self.select_file,
            state="disabled",
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT_SECONDARY,
            font=("Segoe UI", 8),
            relief="flat",
            bd=1,
            cursor="hand2",
            padx=8,
            pady=2,
        )
        self.file_btn.pack(side="left", padx=(10, 0))

        row3 = tk.Frame(inner, bg=Colors.BG)
        row3.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.enable_breaks_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            row3,
            text="Enable breaks every",
            variable=self.enable_breaks_var,
            command=self.toggle_break_settings,
        ).pack(side="left")

        self.tweet_interval_var = tk.StringVar(value="100")
        self.tweet_interval_spin = ttk.Spinbox(
            row3,
            from_=50,
            to=500,
            increment=50,
            textvariable=self.tweet_interval_var,
            width=5,
            state="disabled",
        )
        self.tweet_interval_spin.pack(side="left", padx=(5, 2))

        tk.Label(
            row3,
            text="tweets, pause",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left")

        self.min_break_var = tk.StringVar(value="5")
        self.min_break_spin = ttk.Spinbox(
            row3,
            from_=1,
            to=30,
            textvariable=self.min_break_var,
            width=3,
            state="disabled",
        )
        self.min_break_spin.pack(side="left", padx=(5, 2))

        tk.Label(
            row3, text="-", font=("Segoe UI", 9), bg=Colors.BG, fg=Colors.TEXT
        ).pack(side="left")

        self.max_break_var = tk.StringVar(value="10")
        self.max_break_spin = ttk.Spinbox(
            row3,
            from_=1,
            to=30,
            textvariable=self.max_break_var,
            width=3,
            state="disabled",
        )
        self.max_break_spin.pack(side="left", padx=(2, 2))

        tk.Label(
            row3, text="min", font=("Segoe UI", 9), bg=Colors.BG, fg=Colors.TEXT
        ).pack(side="left")

    def create_search_content(self, parent):
        inner = tk.Frame(parent, bg=Colors.BG, padx=12, pady=10)
        inner.pack(fill="x")
        inner.columnconfigure(1, weight=1)

        tk.Label(
            inner,
            text="Search mode:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).grid(row=0, column=0, sticky="w", pady=4)

        self.mode_var = tk.StringVar(value="Username")
        mode_frame = tk.Frame(inner, bg=Colors.BG)
        mode_frame.grid(row=0, column=1, sticky="w", pady=4)

        self.mode_menu = ttk.Combobox(
            mode_frame,
            textvariable=self.mode_var,
            values=["Username", "Keywords"],
            state="readonly",
            width=12,
        )
        self.mode_menu.pack(side="left")
        self.mode_menu.bind("<<ComboboxSelected>>", self.update_mode)

        self.input_label = tk.Label(
            inner, text="Username:", font=("Segoe UI", 9), bg=Colors.BG, fg=Colors.TEXT
        )
        self.input_label.grid(row=1, column=0, sticky="w", pady=4)

        input_frame = tk.Frame(inner, bg=Colors.BG)
        input_frame.grid(row=1, column=1, sticky="ew", pady=4)
        input_frame.columnconfigure(0, weight=1)

        self.username_entry = ttk.Entry(input_frame)
        self.username_entry.grid(row=0, column=0, sticky="ew")

        self.keyword_entry = ttk.Entry(input_frame)
        self.op_var = tk.StringVar(value="OR")
        self.op_menu = ttk.Combobox(
            input_frame,
            textvariable=self.op_var,
            values=["OR", "AND"],
            state="readonly",
            width=5,
        )

        tk.Label(
            inner,
            text="Date range:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).grid(row=2, column=0, sticky="w", pady=4)

        date_frame = tk.Frame(inner, bg=Colors.BG)
        date_frame.grid(row=2, column=1, sticky="ew", pady=4)

        tk.Label(
            date_frame,
            text="From",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="left")

        self.start_entry = ttk.Entry(date_frame, width=12)
        self.start_entry.pack(side="left", padx=(5, 5))

        self.start_time_entry = ttk.Entry(date_frame, width=9)
        self.start_time_entry.pack(side="left", padx=(0, 15))
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.config(foreground="gray")
        self.start_time_entry.bind(
            "<FocusIn>", lambda e: self._on_time_focus_in(e, "00:00:00")
        )
        self.start_time_entry.bind("<FocusOut>", lambda e: self._validate_time_entry(e))

        tk.Label(
            date_frame,
            text="To",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="left")

        self.end_entry = ttk.Entry(date_frame, width=12)
        self.end_entry.pack(side="left", padx=(5, 5))

        self.end_time_entry = ttk.Entry(date_frame, width=9)
        self.end_time_entry.pack(side="left")
        self.end_time_entry.insert(0, "23:59:59")
        self.end_time_entry.config(foreground="gray")
        self.end_time_entry.bind(
            "<FocusIn>", lambda e: self._on_time_focus_in(e, "23:59:59")
        )
        self.end_time_entry.bind("<FocusOut>", lambda e: self._validate_time_entry(e))

        tk.Label(
            inner,
            text="Format: YYYY-MM-DD (time optional: HH:MM:SS)",
            font=("Segoe UI", 8),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).grid(row=3, column=1, sticky="w")

        cookie_row = tk.Frame(inner, bg=Colors.BG)
        cookie_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        self.cookie_expanded = tk.BooleanVar(value=False)
        self.cookie_toggle_btn = tk.Button(
            cookie_row,
            text="▶ Update Cookies",
            command=self.toggle_cookie_section,
            bg=Colors.BG,
            fg=Colors.PRIMARY,
            font=("Segoe UI", 9),
            relief="flat",
            bd=0,
            cursor="hand2",
        )
        self.cookie_toggle_btn.pack(anchor="w")

        self.cookie_frame = tk.Frame(inner, bg=Colors.BG)
        self.cookie_frame.columnconfigure(0, weight=1)

        self.cookie_text = tk.Text(
            self.cookie_frame,
            height=3,
            font=("Consolas", 9),
            bg=Colors.BG_SECONDARY,
            relief="solid",
            bd=1,
        )
        self.cookie_text.grid(row=0, column=0, sticky="ew", pady=(5, 5))

        save_cookie_btn = tk.Button(
            self.cookie_frame,
            text="Save Cookies",
            command=self.save_cookies,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
        )
        save_cookie_btn.grid(row=1, column=0, sticky="e")

    def create_controls(self, parent):
        parent.columnconfigure(0, weight=1)

        # Status and buttons row - always visible at top
        control_row = tk.Frame(parent, bg=Colors.BG)
        control_row.grid(row=0, column=0, sticky="ew")
        control_row.columnconfigure(0, weight=1)

        self.count_lbl = tk.Label(
            control_row,
            text="Ready",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        )
        self.count_lbl.grid(row=0, column=0, sticky="w")

        btn_frame = tk.Frame(control_row, bg=Colors.BG)
        btn_frame.grid(row=0, column=1, sticky="e")

        self.scrape_button = tk.Button(
            btn_frame,
            text="Start Scraping",
            command=self.start_scrape_thread,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        )
        self.scrape_button.pack(side="left", padx=(0, 8))

        self.stop_btn = tk.Button(
            btn_frame,
            text="Stop",
            command=self.stop_scrape,
            state="disabled",
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        )
        self.stop_btn.pack(side="left")

        # Progress bar BELOW buttons - won't cover the log
        self.progress = ttk.Progressbar(
            parent, mode="indeterminate", style="Blue.Horizontal.TProgressbar"
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.progress.grid_remove()

    def create_log(self, parent):
        log_inner = tk.Frame(parent, bg=Colors.BG)
        log_inner.pack(fill="both", expand=True, padx=1, pady=1)
        log_inner.columnconfigure(0, weight=1)
        log_inner.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(
            log_inner,
            font=("Consolas", 9),
            bg=Colors.BG_SECONDARY,
            relief="flat",
            wrap=tk.WORD,
            height=10,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        clear_btn = tk.Button(
            log_inner,
            text="Clear",
            command=self.clear_logs,
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
            font=("Segoe UI", 8),
            relief="flat",
            bd=0,
            cursor="hand2",
        )
        clear_btn.grid(row=1, column=0, sticky="e", pady=(4, 0))

    def create_links_tab(self):
        tk.Label(
            self.links_tab,
            text="Scrape tweets from a list of tweet URLs",
            font=("Segoe UI", 10),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        file_frame = tk.Frame(self.links_tab, bg=Colors.BG)
        file_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        file_frame.columnconfigure(0, weight=1)

        self.links_file_var = tk.StringVar(value="")
        ttk.Entry(file_frame, textvariable=self.links_file_var, state="readonly").grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )

        browse_btn = tk.Button(
            file_frame,
            text="Browse",
            command=self.select_links_file,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=4,
        )
        browse_btn.grid(row=0, column=1)

        btn_frame = tk.Frame(self.links_tab, bg=Colors.BG)
        btn_frame.grid(row=2, column=0, sticky="e", pady=(0, 15))

        self.links_scrape_btn = tk.Button(
            btn_frame,
            text="Start Link Scrape",
            command=self.start_links_thread,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        )
        self.links_scrape_btn.pack()

        self.create_section_label(self.links_tab, "Activity Log", 3)
        links_log_frame = self.create_card(self.links_tab, 4, expand=True)

        log_inner = tk.Frame(links_log_frame, bg=Colors.BG)
        log_inner.pack(fill="both", expand=True, padx=1, pady=1)
        log_inner.columnconfigure(0, weight=1)
        log_inner.rowconfigure(0, weight=1)

        self.links_log_text = ScrolledText(
            log_inner,
            font=("Consolas", 9),
            bg=Colors.BG_SECONDARY,
            relief="flat",
            wrap=tk.WORD,
            height=10,
        )
        self.links_log_text.grid(row=0, column=0, sticky="nsew")

        tk.Label(
            self.links_tab,
            text="Supported: .txt (one URL per line) or .xlsx (URLs in first column)",
            font=("Segoe UI", 8),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).grid(row=5, column=0, sticky="w", pady=(10, 0))

    # ========================================
    # ERROR RECOVERY DIALOG
    # ========================================
    def _save_current_state_for_recovery(self, context):
        """Save current state when error occurs so progress isn't lost."""
        try:
            state = self.current_scrape_state.copy()
            state.update(context)
            self.state_manager.save_state(state)
            self.log("💾 State saved for recovery")
        except Exception as e:
            self.log(f"⚠️ Could not save recovery state: {e}")

    def _show_error_recovery_dialog(self, error_type, error_msg, context=None):
        context = context or {}
        tweets_so_far = context.get("tweets_scraped", "Unknown")
        self._save_current_state_for_recovery(context)
        self.user_action = None
        dialog_closed = threading.Event()

        def show_dialog():
            dialog = tk.Toplevel(self.root)
            dialog.title("Action Required")
            dialog.geometry("500x400")
            dialog.resizable(False, False)
            dialog.transient(self.root)
            dialog.grab_set()
            dialog.configure(bg=Colors.BG)
            dialog.protocol("WM_DELETE_WINDOW", lambda: None)

            try:
                icon_path = resource_path(os.path.join("assets", "logo.ico"))
                if os.path.exists(icon_path):
                    dialog.iconbitmap(icon_path)
            except:
                pass

            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - 250
            y = (dialog.winfo_screenheight() // 2) - 200
            dialog.geometry(f"500x400+{x}+{y}")

            main = tk.Frame(dialog, bg=Colors.BG, padx=25, pady=20)
            main.pack(fill="both", expand=True)

            if error_type == "cookie":
                title = "🔑 Authentication Required"
            elif error_type == "network":
                title = "🔌 Connection Lost"
            else:
                title = "⚠️ Error Occurred"

            tk.Label(
                main,
                text=title,
                font=("Segoe UI", 14, "bold"),
                bg=Colors.BG,
                fg=Colors.TEXT,
            ).pack(anchor="w")

            tk.Label(
                main,
                text=f"Progress: {tweets_so_far} tweets saved",
                font=("Segoe UI", 9),
                bg=Colors.BG,
                fg=Colors.TEXT_SECONDARY,
            ).pack(anchor="w", pady=(2, 10))

            error_frame = tk.Frame(main, bg=Colors.BG_SECONDARY, padx=10, pady=10)
            error_frame.pack(fill="x", pady=(0, 15))
            tk.Label(
                error_frame,
                text=error_msg[:150],
                font=("Segoe UI", 9),
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT,
                wraplength=430,
                justify="left",
            ).pack(anchor="w")

            cookie_text = None
            resume_btn = None

            if error_type == "cookie":
                tk.Label(
                    main,
                    text="Paste new cookies below:",
                    font=("Segoe UI", 9),
                    bg=Colors.BG,
                    fg=Colors.TEXT,
                ).pack(anchor="w", pady=(0, 5))
                cookie_text = tk.Text(
                    main,
                    height=5,
                    font=("Consolas", 9),
                    bg=Colors.BG_SECONDARY,
                    relief="solid",
                    bd=1,
                )
                cookie_text.pack(fill="x", pady=(0, 10))
            elif error_type == "network":
                tk.Label(
                    main,
                    text="Check your internet connection and try again.",
                    font=("Segoe UI", 9),
                    bg=Colors.BG,
                    fg=Colors.TEXT,
                ).pack(anchor="w", pady=(0, 10))

            feedback = tk.Label(
                main,
                text="",
                font=("Segoe UI", 9),
                bg=Colors.BG,
                fg=Colors.TEXT_SECONDARY,
            )
            feedback.pack(anchor="w", pady=(0, 10))

            def update_and_resume():
                if error_type == "cookie" and cookie_text:
                    raw = cookie_text.get("1.0", tk.END).strip()
                    if not raw:
                        feedback.config(
                            text="Please paste cookies first", fg=Colors.ERROR
                        )
                        return
                    feedback.config(text="Validating...", fg=Colors.TEXT_SECONDARY)
                    dialog.update()
                    if convert_editthiscookie_to_twikit_format(raw):
                        self.user_action = "resume"
                        close_dialog()
                    else:
                        feedback.config(
                            text="Invalid format. Try again.", fg=Colors.ERROR
                        )
                        cookie_text.delete("1.0", tk.END)
                else:
                    self.user_action = "resume"
                    close_dialog()

            def test_conn():
                feedback.config(text="Testing...", fg=Colors.TEXT_SECONDARY)
                dialog.update()
                import urllib.request

                try:
                    urllib.request.urlopen("https://google.com", timeout=5)
                    feedback.config(
                        text="✓ Connected! Click Resume.", fg=Colors.SUCCESS
                    )
                    if resume_btn:
                        resume_btn.config(state="normal", bg=Colors.PRIMARY)
                except:
                    feedback.config(text="✗ Still offline", fg=Colors.ERROR)

            def stop_action():
                self.user_action = "stop"
                close_dialog()

            def retry_action():
                self.user_action = "retry"
                close_dialog()

            def close_dialog():
                dialog.grab_release()
                dialog.destroy()
                dialog_closed.set()

            btn_frame = tk.Frame(main, bg=Colors.BG)
            btn_frame.pack(fill="x", pady=(10, 0))

            stop_btn = tk.Button(
                btn_frame,
                text="Stop & Save",
                command=stop_action,
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT,
                font=("Segoe UI", 9),
                relief="flat",
                cursor="hand2",
                padx=12,
                pady=6,
            )
            stop_btn.pack(side="left")

            if error_type == "network":
                test_btn = tk.Button(
                    btn_frame,
                    text="Test Connection",
                    command=test_conn,
                    bg=Colors.BG_SECONDARY,
                    fg=Colors.TEXT,
                    font=("Segoe UI", 9),
                    relief="flat",
                    cursor="hand2",
                    padx=12,
                    pady=6,
                )
                test_btn.pack(side="right", padx=(8, 0))

                resume_btn = tk.Button(
                    btn_frame,
                    text="Resume",
                    command=update_and_resume,
                    state="disabled",
                    bg=Colors.BG_SECONDARY,
                    fg=Colors.TEXT_SECONDARY,
                    font=("Segoe UI", 9),
                    relief="flat",
                    cursor="hand2",
                    padx=12,
                    pady=6,
                )
                resume_btn.pack(side="right")
            elif error_type == "cookie":
                update_btn = tk.Button(
                    btn_frame,
                    text="Update & Resume",
                    command=update_and_resume,
                    bg=Colors.PRIMARY,
                    fg="white",
                    font=("Segoe UI", 9),
                    relief="flat",
                    cursor="hand2",
                    padx=12,
                    pady=6,
                )
                update_btn.pack(side="right")
            else:
                retry_btn = tk.Button(
                    btn_frame,
                    text="Retry",
                    command=retry_action,
                    bg=Colors.PRIMARY,
                    fg="white",
                    font=("Segoe UI", 9),
                    relief="flat",
                    cursor="hand2",
                    padx=12,
                    pady=6,
                )
                retry_btn.pack(side="right")

            dialog.focus_force()
            if cookie_text:
                cookie_text.focus()

        self.root.after(0, show_dialog)
        dialog_closed.wait(timeout=3600)
        return self.user_action

    def _wait_for_user_action(self, error_type, error_msg, context=None):
        if error_type == "cookie":
            self.paused_for_cookies = True
        elif error_type == "network":
            self.paused_for_network = True
        else:
            self.paused_for_error = True

        action = self._show_error_recovery_dialog(error_type, error_msg, context)

        self.paused_for_cookies = False
        self.paused_for_network = False
        self.paused_for_error = False
        return action

    # ========================================
    # HELPER METHODS
    # ========================================
    def toggle_cookie_section(self):
        if self.cookie_expanded.get():
            self.cookie_frame.grid_remove()
            self.cookie_toggle_btn.config(text="▶ Update Cookies")
            self.cookie_expanded.set(False)
        else:
            self.cookie_frame.grid(
                row=5, column=0, columnspan=2, sticky="ew", pady=(5, 0)
            )
            self.cookie_toggle_btn.config(text="▼ Update Cookies")
            self.cookie_expanded.set(True)

    def toggle_batch(self):
        on = self.batch_var.get()
        state = "normal" if on else "disabled"
        self.file_btn.config(state=state)
        self.mode_menu.config(state="disabled" if on else "readonly")
        self.username_entry.config(state="disabled" if on else "normal")

    def toggle_break_settings(self):
        state = "normal" if self.enable_breaks_var.get() else "disabled"
        self.tweet_interval_spin.config(state=state)
        self.min_break_spin.config(state=state)
        self.max_break_spin.config(state=state)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_dir.set(folder)

    def select_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text/CSV", "*.txt;*.csv"), ("All", "*.*")]
        )
        if path:
            self.file_path = path
            self.log(f"✓ Loaded: {os.path.basename(path)}")

    def select_links_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text", "*.txt"), ("Excel", "*.xlsx;*.xls"), ("All", "*.*")]
        )
        if path:
            self.links_file_path = path
            self.links_file_var.set(path)
            self.links_log(f"✓ Loaded: {os.path.basename(path)}")

    def update_mode(self, *_):
        if self.mode_var.get() == "Username":
            self.input_label.config(text="Username:")
            self.username_entry.grid(row=0, column=0, sticky="ew")
            self.keyword_entry.grid_remove()
            self.op_menu.grid_remove()
        else:
            self.input_label.config(text="Keywords:")
            self.username_entry.grid_remove()
            self.keyword_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
            self.op_menu.grid(row=0, column=1)

    def _on_time_focus_in(self, event, default):
        w = event.widget
        if w.get() == default:
            w.delete(0, tk.END)
            w.config(foreground="black")

    def _validate_time_entry(self, event):
        w = event.widget
        val = w.get().strip()
        default = "00:00:00" if w == self.start_time_entry else "23:59:59"
        if not val:
            w.insert(0, default)
            w.config(foreground="gray")
            return
        try:
            datetime.strptime(val, "%H:%M:%S")
            w.config(foreground="black")
        except:
            try:
                datetime.strptime(val, "%H:%M")
                w.delete(0, tk.END)
                w.insert(0, f"{val}:00")
                w.config(foreground="black")
            except:
                w.delete(0, tk.END)
                w.insert(0, default)
                w.config(foreground="gray")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)

    def links_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.links_log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.links_log_text.see(tk.END)

    def clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def save_cookies(self):
        raw = self.cookie_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("Empty", "Paste cookie JSON first.")
            return
        if convert_editthiscookie_to_twikit_format(raw):
            self.log("✓ Cookies saved")
            messagebox.showinfo("Success", "Cookies saved!")
            self.toggle_cookie_section()
        else:
            messagebox.showerror("Error", "Invalid cookie format.")

    def get_break_settings(self):
        if not self.enable_breaks_var.get():
            return None
        try:
            return {
                "enabled": True,
                "tweet_interval": int(self.tweet_interval_var.get()),
                "min_break_minutes": int(self.min_break_var.get()),
                "max_break_minutes": int(self.max_break_var.get()),
            }
        except:
            return None

    def save_scrape_state(self, mode, **kwargs):
        """
        FIX: Save complete state including seen_tweet_ids and output_path.
        """
        state = {"mode": mode, **kwargs}
        self.current_scrape_state = state
        self.state_manager.save_state(state)

    def check_for_saved_state(self):
        if self.state_manager.has_saved_state():
            summary = self.state_manager.get_state_summary()
            if messagebox.askyesno(
                "Resume?", f"Found incomplete session:\n\n{summary}\n\nResume?"
            ):
                self.resume_from_state()
            else:
                self.state_manager.clear_state()

    def resume_from_state(self):
        state = self.state_manager.load_state()
        if not state:
            return
        mode = state.get("mode")
        if mode == "single":
            self.resume_single_scrape(state)
        elif mode == "batch":
            self.resume_batch_scrape(state)
        elif mode == "links":
            self.resume_links_scrape(state)

    def resume_single_scrape(self, state):
        settings = state.get("settings", {})
        self._start_scrape_from_state(state, settings)

    def resume_batch_scrape(self, state):
        settings = state.get("settings", {})
        self._start_scrape_from_state(state, settings)

    def resume_links_scrape(self, state):
        self.links_file_path = state.get("links_file_path")
        self.links_file_var.set(self.links_file_path or "")
        settings = state.get("settings", {})
        fmt = settings.get("export_format", "excel").lower()
        save_dir = settings.get("save_dir", self.save_dir.get())
        threading.Thread(
            target=self._run_links,
            args=(self.links_file_path, fmt, save_dir, None),
            daemon=True,
        ).start()

    def _start_scrape_from_state(self, state, settings):
        start = settings.get("start_date", "")
        end = settings.get("end_date", "")
        fmt = settings.get("export_format", "excel").lower()
        save_dir = settings.get("save_dir", self.save_dir.get())

        mode = state.get("mode")
        if mode == "batch":
            usernames = state.get("usernames", [])
            idx = state.get("current_index", 0)
            target = ("batch", usernames[idx:])
        else:
            user = state.get("current_username")
            kws = state.get("keywords")
            target = ("single", user, kws)

        self.current_task_type = "main"
        self._stop_requested = False
        self._is_running = True
        self.scrape_button.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid()
        self.progress.start(30)
        threading.Thread(
            target=self._run_scrape,
            args=(target, start, end, fmt, save_dir, None),
            daemon=True,
        ).start()

    # ========================================
    # SCRAPING METHODS
    # ========================================
    def _run_scrape(self, target, start, end, fmt, save_dir, break_settings):
        def progress_cb(msg):
            if isinstance(msg, str):
                self.log(msg)
            else:
                self.root.after(
                    0,
                    lambda: self.count_lbl.config(
                        text=f"Scraped: {msg}", fg=Colors.SUCCESS
                    ),
                )

        def cookie_cb(msg):
            self.log(f"🔑 {msg}")

        def network_cb(msg):
            self.log(f"🔌 {msg}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if target[0] == "batch":

                async def batch():
                    total = 0
                    users = target[1]
                    all_seen_ids = set()  # ADD THIS LINE

                    for i, u in enumerate(users):
                        if (
                            self._should_stop()
                        ):  # FIX: Use _should_stop() not task.done()
                            break
                        progress_cb(f"User {i+1}/{len(users)}: @{u}")

                        # Save state BEFORE scraping (without output_path yet)
                        self.save_scrape_state(
                            "batch",
                            usernames=users,
                            current_index=i,
                            current_username=u,
                            tweets_scraped=total,
                            seen_tweet_ids=list(all_seen_ids),
                            settings={
                                "start_date": start,
                                "end_date": end,
                                "export_format": fmt,
                                "save_dir": save_dir,
                            },
                        )

                        retry = 0
                        while retry < 5:
                            try:
                                out, cnt, seen_ids = await scrape_tweets(
                                    username=u,
                                    start_date=start,
                                    end_date=end,
                                    export_format=fmt,
                                    progress_callback=progress_cb,
                                    should_stop_callback=self._should_stop,
                                    cookie_expired_callback=cookie_cb,
                                    network_error_callback=network_cb,
                                    save_dir=save_dir,
                                    break_settings=break_settings,
                                )
                                total += cnt
                                all_seen_ids.update(seen_ids)  # Add the returned IDs

                                # Save state AFTER scraping (now with output_path)
                                self.save_scrape_state(
                                    "batch",
                                    usernames=users,
                                    current_index=i
                                    + 1,  # Increment because this user is done
                                    current_username=u,
                                    tweets_scraped=total,
                                    seen_tweet_ids=list(all_seen_ids),
                                    output_path=out,
                                    settings={
                                        "start_date": start,
                                        "end_date": end,
                                        "export_format": fmt,
                                        "save_dir": save_dir,
                                    },
                                )

                                progress_cb(f"✓ {cnt} tweets for @{u}")
                                break
                            except CookieExpiredError:
                                action = self._wait_for_user_action(
                                    "cookie",
                                    "Cookies expired",
                                    {
                                        "tweets_scraped": total,
                                        "seen_tweet_ids": list(all_seen_ids),
                                    },
                                )
                                if action == "stop":
                                    return total
                                retry += 1
                            except NetworkError as e:
                                action = self._wait_for_user_action(
                                    "network", str(e), {"tweets_scraped": total}
                                )
                                if action == "stop":
                                    return total
                                retry += 1
                            except Exception as e:
                                action = self._wait_for_user_action(
                                    "unknown", str(e), {"tweets_scraped": total}
                                )
                                if action == "stop":
                                    return total
                                retry += 1
                    self.state_manager.clear_state()
                    return total

                self.task = loop.create_task(batch())
                total = loop.run_until_complete(self.task)
                self.log(f"✓ Done! {total} tweets total")
                messagebox.showinfo("Complete", f"Scraped {total} tweets!")
            else:
                _, user, kws = target

                async def single():
                    # FIX: Save complete state
                    self.save_scrape_state(
                        "single",
                        current_username=user,
                        keywords=kws,
                        tweets_scraped=0,  # Will be updated
                        seen_tweet_ids=[],  # Will be updated
                        output_path=None,  # Will be updated
                        settings={
                            "start_date": start,
                            "end_date": end,
                            "export_format": fmt,
                            "save_dir": save_dir,
                            "use_and": self.op_var.get() == "AND",
                        },
                    )
                    retry = 0
                    while retry < 5:
                        try:
                            out, cnt, _ = await scrape_tweets(
                                username=user,
                                start_date=start,
                                end_date=end,
                                keywords=kws,
                                use_and=self.op_var.get() == "AND",
                                export_format=fmt,
                                progress_callback=progress_cb,
                                should_stop_callback=self._should_stop,
                                cookie_expired_callback=cookie_cb,
                                network_error_callback=network_cb,
                                save_dir=save_dir,
                                break_settings=break_settings,
                            )
                            self.state_manager.clear_state()
                            return out, cnt
                        except CookieExpiredError:
                            action = self._wait_for_user_action(
                                "cookie", "Cookies expired", {}
                            )
                            if action == "stop":
                                return None, 0
                            retry += 1
                        except NetworkError as e:
                            action = self._wait_for_user_action("network", str(e), {})
                            if action == "stop":
                                return None, 0
                            retry += 1
                        except Exception as e:
                            action = self._wait_for_user_action("unknown", str(e), {})
                            if action == "stop":
                                return None, 0
                            retry += 1
                    return None, 0

                self.task = loop.create_task(single())
                out, cnt = loop.run_until_complete(self.task)
                if out:
                    self.log(f"✓ Done! {cnt} tweets saved")
                    messagebox.showinfo(
                        "Complete", f"Scraped {cnt} tweets!\n\nSaved to:\n{out}"
                    )
        except asyncio.CancelledError:
            self.log("Cancelled")
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self._cleanup_after_scrape()

    def _run_links(self, path, fmt, save_dir, break_settings):
        def progress_cb(msg):
            if isinstance(msg, str):
                self.links_log(msg)
            else:
                self.root.after(
                    0,
                    lambda: self.count_lbl.config(
                        text=f"Scraped: {msg}", fg=Colors.SUCCESS
                    ),
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:

            async def links_task():
                retry = 0
                while retry < 5:
                    try:
                        out, cnt, failed, _ = await scrape_tweet_links_file(
                            file_path=path,
                            export_format=fmt,
                            save_dir=save_dir,
                            progress_callback=progress_cb,
                            should_stop_callback=self._should_stop,
                            break_settings=break_settings,
                        )
                        self.state_manager.clear_state()
                        return out, cnt, failed
                    except CookieExpiredError:
                        action = self._wait_for_user_action(
                            "cookie", "Cookies expired", {}
                        )
                        if action == "stop":
                            return None, 0, 0
                        retry += 1
                    except NetworkError as e:
                        action = self._wait_for_user_action("network", str(e), {})
                        if action == "stop":
                            return None, 0, 0
                        retry += 1
                    except Exception as e:
                        action = self._wait_for_user_action("unknown", str(e), {})
                        if action == "stop":
                            return None, 0, 0
                        retry += 1
                return None, 0, 0

            self.task = loop.create_task(links_task())
            out, cnt, failed = loop.run_until_complete(self.task)
            if out:
                self.links_log(f"✓ Done! {cnt} scraped, {failed} failed")
                messagebox.showinfo("Complete", f"Scraped {cnt} tweets!")
        except asyncio.CancelledError:
            self.links_log("Cancelled")
        except Exception as e:
            self.links_log(f"Error: {e}")
        finally:
            self._cleanup_after_scrape()

    def start_scrape_thread(self):
        if self._is_running:
            messagebox.showwarning("Busy", "Already running.")
            return

        start = self.start_entry.get().strip()
        end = self.end_entry.get().strip()
        if not start or not end:
            messagebox.showerror("Missing", "Enter start and end dates.")
            return

        try:
            st = self.start_time_entry.get().strip()
            et = self.end_time_entry.get().strip()
            if st == "00:00:00" or not st:
                st = "00:00:00"
            if et == "23:59:59" or not et:
                et = "23:59:59"

            start_dt = datetime.strptime(f"{start} {st}", "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(f"{end} {et}", "%Y-%m-%d %H:%M:%S")

            if start_dt >= end_dt:
                messagebox.showerror("Invalid", "Start must be before end.")
                return

            start = start_dt.strftime("%Y-%m-%d_%H:%M:%S")
            end = end_dt.strftime("%Y-%m-%d_%H:%M:%S")
        except Exception as e:
            messagebox.showerror("Invalid", f"Date format error: {e}")
            return

        fmt = self.format_var.get().lower()
        save_dir = self.save_dir.get()
        break_settings = self.get_break_settings()

        if self.batch_var.get():
            if not self.file_path:
                messagebox.showwarning("Missing", "Select a username file.")
                return
            with open(self.file_path, encoding="utf-8") as f:
                users = [
                    u.strip()
                    for u in f.read().replace("\n", ",").split(",")
                    if u.strip()
                ]
            if not users:
                messagebox.showwarning("Empty", "No usernames found.")
                return
            target = ("batch", users)
        else:
            mode = self.mode_var.get()
            if mode == "Username":
                user = self.username_entry.get().strip()
                if not user:
                    messagebox.showwarning("Missing", "Enter a username.")
                    return
                target = ("single", user, None)
            else:
                kws = [
                    k.strip() for k in self.keyword_entry.get().split(",") if k.strip()
                ]
                if not kws:
                    messagebox.showwarning("Missing", "Enter keywords.")
                    return
                target = ("single", None, kws)

        self.current_task_type = "main"
        self.scrape_button.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid()
        self.progress.start(30)
        self.count_lbl.config(text="Starting...", fg=Colors.PRIMARY)
        self.clear_logs()
        self.log("Starting scrape...")
        self._stop_requested = False
        self._is_running = True

        threading.Thread(
            target=self._run_scrape,
            args=(target, start, end, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def start_links_thread(self):
        if self._is_running:
            messagebox.showwarning("Busy", "Already running.")
            return

        if not self.links_file_path:
            messagebox.showwarning("Missing", "Select a links file.")
            return

        fmt = self.format_var.get().lower()
        save_dir = self.save_dir.get()
        break_settings = self.get_break_settings()

        self.current_task_type = "links"
        self.links_scrape_btn.config(state="disabled")
        self.progress.grid()
        self.progress.start(30)
        self.links_log("Starting link scrape...")
        self._stop_requested = False
        self._is_running = True

        threading.Thread(
            target=self._run_links,
            args=(self.links_file_path, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def stop_scrape(self):
        """FIX: Use explicit stop flag instead of just task.cancel()."""
        self._stop_requested = True
        self.log("🛑 Stop requested... (will stop after current operation)")

        # Also cancel the task if it exists
        if self.task and not self.task.done():
            self.task.cancel()

    def _cleanup_after_scrape(self):
        """Common cleanup after any scrape operation."""
        self.progress.stop()
        self.progress.grid_remove()
        self.scrape_button.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.links_scrape_btn.config(state="normal")
        self.count_lbl.config(text="Ready", fg=Colors.TEXT_SECONDARY)
        self.task = None
        self.loop = None
        self._stop_requested = False
        self._is_running = False
        self.current_scrape_state = {}

    def show_guide(self):
        guide = tk.Toplevel(self.root)
        guide.title("Chi Tweet Scraper - User Guide")
        guide.geometry("680x650")
        guide.configure(bg=Colors.BG)
        guide.resizable(True, True)

        try:
            icon_path = resource_path(os.path.join("assets", "logo.ico"))
            if os.path.exists(icon_path):
                guide.iconbitmap(icon_path)
        except:
            pass

        guide.update_idletasks()
        x = (guide.winfo_screenwidth() // 2) - 340
        y = (guide.winfo_screenheight() // 2) - 325
        guide.geometry(f"680x650+{x}+{y}")

        main = tk.Frame(guide, bg=Colors.BG, padx=20, pady=15)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=Colors.PRIMARY, height=50)
        header.pack(fill="x", pady=(0, 15))
        header.pack_propagate(False)
        tk.Label(
            header,
            text="📖 Chi Tweet Scraper - User Guide",
            font=("Segoe UI", 14, "bold"),
            bg=Colors.PRIMARY,
            fg="white",
        ).pack(pady=12)

        help_text = """🎯 QUICK START
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Save your Twitter cookies (click "▶ Update Cookies")
2. Enter a username OR keywords (comma-separated)
3. Set your date range (YYYY-MM-DD format)
4. Click "Start Scraping" and watch the Activity Log!


🔑 COOKIE AUTHENTICATION (Required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Twitter requires authentication to access tweets. Here's how:

1. Log in to Twitter/X.com in your browser
2. Install the "Cookie-Editor" browser extension
   • Chrome: Search "Cookie-Editor" in Chrome Web Store
   • Firefox: Search "Cookie-Editor" in Add-ons
3. Go to Twitter/X.com and click the Cookie-Editor icon
4. Click "Export" → "Export as JSON" (copy to clipboard)
5. In this app, click "▶ Update Cookies"
6. Paste the JSON and click "Save Cookies"

⚠️ Cookies expire after 1-2 weeks. When they expire, a popup 
   will appear - just paste new cookies to continue!


🔍 SEARCH MODES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USERNAME MODE:
• Enter a Twitter username (with or without @)
• Scrapes all tweets from that user in the date range
• Example: elonmusk or @elonmusk

KEYWORDS MODE:
• Enter keywords separated by commas
• OR: Finds tweets containing ANY keyword
• AND: Finds tweets containing ALL keywords
• Example: "AI, machine learning, neural network"


📅 DATE & TIME FILTERING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Date format: YYYY-MM-DD (e.g., 2024-06-15)
• Time format: HH:MM:SS or HH:MM (optional, 24-hour)
• Leave time fields as default for full-day range

Examples:
• Full day: 2024-01-01 to 2024-01-31 (uses 00:00:00 - 23:59:59)
• Specific hours: 09:00 to 17:00
• Precise: 2024-12-25 14:30:00 to 2024-12-25 18:00:00


📦 BATCH MODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scrape multiple usernames at once:
1. Create a .txt file with usernames (one per line or comma-separated)
2. Check "Batch mode" checkbox
3. Click "Select File" and choose your file
4. Each user's tweets are saved to a separate file


🔗 SCRAPE BY LINKS TAB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Get detailed data from specific tweets:
1. Create a .txt file with tweet URLs (one per line)
   OR use .xlsx with URLs in the first column
2. Switch to "Scrape by Links" tab
3. Select your file and click "Start Link Scrape"

Supported URL formats:
• https://twitter.com/user/status/123456789
• https://x.com/user/status/123456789


⏸️ RATE LIMIT PREVENTION (Breaks)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enable random breaks to avoid Twitter's rate limits:
• Every X tweets: How often to pause (default: 100)
• Break duration: Random time between min-max minutes

Recommended settings for large scrapes:
• 500+ tweets: Every 100 tweets, 5-10 min breaks
• 2000+ tweets: Every 100 tweets, 8-15 min breaks


🛡️ ROBUST ERROR HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This scraper is designed to NEVER crash or lose your data:

• Network errors: Auto-retry with progressive delays (10s → 15min)
• Rate limits: Automatically waits 15 minutes, then continues
• Cookie expiry: Pauses and shows popup to paste new cookies
• Duplicate cookies: Automatically cleaned from cookie file
• API errors: Retries up to 10 times with backoff
• Unknown errors: Shows dialog with Retry/Stop options

✅ Your progress is auto-saved every 25 tweets
✅ You can resume interrupted scrapes when you restart the app


📊 EXPORT FORMATS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXCEL (.xlsx):
• Best for viewing, filtering, and sorting
• Preserves formatting
• Works with Excel, Google Sheets, LibreOffice

CSV (.csv):
• Faster for very large datasets (10,000+ tweets)
• UTF-8 encoded for compatibility
• Works with any spreadsheet or data tool

Exported columns: Date, Username, Display Name, Text, Retweets, 
Likes, Replies, Quotes, Views, Tweet ID, Tweet URL


💡 PRO TIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Start with a small date range (1-2 days) to test
• Watch the Activity Log for real-time progress
• Enable breaks for any scrape over 500 tweets
• If you see repeated errors, try updating your cookies
• Use CSV format for datasets over 10,000 tweets
• The scraper automatically handles timeline gaps


📹 VIDEO TUTORIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Setup Guide: https://youtu.be/RKX2sgQVgBg
Full Tutorial: https://youtu.be/AbdpX6QZLm4


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Made with ❤️ by OJ | Version 1.1.0 | January 2025
"""

        text_frame = tk.Frame(main, bg=Colors.BG)
        text_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        text = tk.Text(
            text_frame,
            font=("Consolas", 9),
            bg=Colors.BG_SECONDARY,
            relief="flat",
            wrap=tk.WORD,
            padx=15,
            pady=10,
            yscrollcommand=scrollbar.set,
        )
        text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text.yview)

        text.insert("1.0", help_text)
        text.config(state="disabled")

        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(15, 0))

        tk.Button(
            btn_frame,
            text="📹 Setup Video",
            command=lambda: webbrowser.open("https://youtu.be/RKX2sgQVgBg"),
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_frame,
            text="📹 Full Tutorial",
            command=lambda: webbrowser.open("https://youtu.be/AbdpX6QZLm4"),
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="left")

        tk.Button(
            btn_frame,
            text="Close",
            command=guide.destroy,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="right")


if __name__ == "__main__":
    cookies_dir = resource_path("cookies")
    exports_dir = resource_path(os.path.join("data", "exports"))
    os.makedirs(cookies_dir, exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)

    root = tk.Tk()
    app = TweetScraperApp(root)
    root.mainloop()
