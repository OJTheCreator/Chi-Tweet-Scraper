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
import time as time_module
from PIL import Image, ImageTk
import webbrowser
from src.state_manager import StateManager
from src.create_cookie import convert_editthiscookie_to_twikit_format

# Features module imports
try:
    from src.utils.features import (
        SettingsManager,
        HistoryManager,
        ScrapeQueue,
        QueueItem,
        TweetFilters,
        ScrapeAnalytics,
        calculate_analytics,
        format_analytics_summary,
        get_date_presets,
        estimate_cost,
        format_cost,
        # New v1.4 imports
        ExportFormat,
        export_tweets,
        generate_filename,
        RetryConfig,
        RetryHandler,
        AppSettings,
        load_app_settings,
        save_app_settings,
    )

    FEATURES_AVAILABLE = True
except ImportError:
    FEATURES_AVAILABLE = False

# API Module imports
try:
    from src.api import (
        get_scraper,
        APIProviderType,
        get_available_providers,
        get_provider_info,
        is_provider_available,
        test_api_key,
        ScrapedTweet,
        APISearchResult,
        APIAuthenticationError,
        APIRateLimitError,
        APINetworkError,
    )
    from src.config import (
        get_api_key_manager,
        get_api_key,
        set_api_key,
    )

    API_MODULE_AVAILABLE = True
except ImportError:
    API_MODULE_AVAILABLE = False


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)


# ========================================
# THEME SYSTEM (Light/Dark Mode)
# ========================================
class Colors:
    """Color theme with dark mode support."""

    _dark_mode = False

    # Light theme (default)
    PRIMARY = "#2563eb"
    PRIMARY_DARK = "#1d4ed8"
    PRIMARY_LIGHT = "#3b82f6"
    BG = "#ffffff"
    BG_SECONDARY = "#f8fafc"
    BORDER = "#e2e8f0"
    TEXT = "#1e293b"
    TEXT_SECONDARY = "#64748b"
    SUCCESS = "#22c55e"
    ERROR = "#ef4444"
    WARNING = "#f59e0b"

    @classmethod
    def set_dark_mode(cls, enabled: bool):
        cls._dark_mode = enabled
        if enabled:
            cls.PRIMARY = "#3b82f6"
            cls.PRIMARY_DARK = "#2563eb"
            cls.PRIMARY_LIGHT = "#60a5fa"
            cls.BG = "#1e1e2e"
            cls.BG_SECONDARY = "#2a2a3c"
            cls.BORDER = "#404052"
            cls.TEXT = "#e2e8f0"
            cls.TEXT_SECONDARY = "#a1a1b5"
            cls.SUCCESS = "#4ade80"
            cls.ERROR = "#f87171"
            cls.WARNING = "#fbbf24"
        else:
            cls.PRIMARY = "#2563eb"
            cls.PRIMARY_DARK = "#1d4ed8"
            cls.PRIMARY_LIGHT = "#3b82f6"
            cls.BG = "#ffffff"
            cls.BG_SECONDARY = "#f8fafc"
            cls.BORDER = "#e2e8f0"
            cls.TEXT = "#1e293b"
            cls.TEXT_SECONDARY = "#64748b"
            cls.SUCCESS = "#22c55e"
            cls.ERROR = "#ef4444"
            cls.WARNING = "#f59e0b"

    @classmethod
    def is_dark_mode(cls):
        return cls._dark_mode


class TweetScraperApp:
    def __init__(self, root):
        self.root = root

        # Load app settings (including dark mode)
        if FEATURES_AVAILABLE:
            self.app_settings = load_app_settings()
            Colors.set_dark_mode(self.app_settings.dark_mode)
        else:
            self.app_settings = None

        root.title("Chi Tweet Scraper 1.4.0   (Data Creator)")
        root.geometry("850x850")
        root.resizable(True, True)
        root.minsize(800, 800)
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

        # API Mode tracking
        self.api_scraper = None  # Current API scraper instance
        self.scraping_method = tk.StringVar(value="cookie")  # "cookie" or API provider

        # Feature managers
        if FEATURES_AVAILABLE:
            self.settings_manager = SettingsManager()
            self.history_manager = HistoryManager()
            self.scrape_queue = ScrapeQueue()
            self.filters = TweetFilters()
        else:
            self.settings_manager = None
            self.history_manager = None
            self.scrape_queue = None
            self.filters = None

        # Scrape tracking for analytics
        self._scrape_start_time = None
        self._last_scraped_tweets = []  # Store for preview/analytics

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
        self.root.after(
            600, self._load_last_settings
        )  # Load settings after UI is built

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
            text="by OJTheCreator",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(anchor="w")

        # Right side buttons frame
        btn_frame = tk.Frame(header, bg=Colors.BG)
        btn_frame.grid(row=0, column=2)

        # Dark mode toggle
        self.dark_mode_var = tk.BooleanVar(value=Colors.is_dark_mode())
        self.dark_mode_btn = tk.Button(
            btn_frame,
            text="🌙" if not Colors.is_dark_mode() else "☀️",
            command=self._toggle_dark_mode,
            bg=Colors.BG,
            fg=Colors.TEXT,
            font=("Segoe UI", 12),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=5,
        )
        self.dark_mode_btn.pack(side="left", padx=(0, 5))

        help_btn = tk.Button(
            btn_frame,
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
        help_btn.pack(side="left")

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
        inner = tk.Frame(parent, bg=Colors.BG, padx=12, pady=8)
        inner.pack(fill="x")
        inner.columnconfigure(0, weight=1)

        # ========================================
        # ROW 1: Method + Export (all on one line)
        # ========================================
        row1 = tk.Frame(inner, bg=Colors.BG)
        row1.pack(fill="x", pady=(0, 6))

        # Left side: Scraping Method
        method_frame = tk.Frame(row1, bg=Colors.BG)
        method_frame.pack(side="left")

        tk.Label(
            method_frame,
            text="Method:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left", padx=(0, 5))

        # Build scraping method options
        self.method_options = self._build_scraping_method_options()
        self.method_display_map = {opt[0]: opt[1] for opt in self.method_options}
        method_values = [opt[0] for opt in self.method_options]

        self.method_var = tk.StringVar(value=method_values[0])
        self.method_combo = ttk.Combobox(
            method_frame,
            textvariable=self.method_var,
            values=method_values,
            state="readonly",
            width=28,
        )
        self.method_combo.pack(side="left")
        self.method_combo.bind("<<ComboboxSelected>>", self._on_method_changed)

        # Config button (interchangeable: 🍪 for cookie, ⚙ for API)
        self.config_btn = tk.Button(
            method_frame,
            text="🍪",
            command=self._on_config_btn_click,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 10),
            relief="flat",
            bd=1,
            cursor="hand2",
            width=2,
        )
        self.config_btn.pack(side="left", padx=(4, 0))

        # API status indicator (compact)
        self.api_status_lbl = tk.Label(
            method_frame,
            text="",
            font=("Segoe UI", 8),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        )
        self.api_status_lbl.pack(side="left", padx=(6, 0))
        self._update_api_status()
        self._update_config_button()

        # Separator
        tk.Frame(row1, bg=Colors.BORDER, width=1).pack(
            side="left", fill="y", padx=15, pady=2
        )

        # Right side: Export format + directory
        export_frame = tk.Frame(row1, bg=Colors.BG)
        export_frame.pack(side="left", fill="x", expand=True)

        tk.Label(
            export_frame,
            text="Export:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left", padx=(0, 5))

        # Export format with more options
        export_formats = ["Excel", "CSV", "JSON", "SQLite", "HTML", "Markdown"]
        self.format_var = tk.StringVar(value="Excel")
        fmt_combo = ttk.Combobox(
            export_frame,
            textvariable=self.format_var,
            values=export_formats,
            state="readonly",
            width=9,
        )
        fmt_combo.pack(side="left", padx=(0, 8))

        folder_btn = tk.Button(
            export_frame,
            text="📁",
            command=self.choose_folder,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            bd=1,
            cursor="hand2",
            width=2,
        )
        folder_btn.pack(side="right")

        # Save directory (takes remaining space)
        # Check if save_dir has a value, if not show placeholder
        if not self.save_dir.get() or not os.path.exists(self.save_dir.get()):
            self.save_dir.set("")

        self.save_dir_entry = ttk.Entry(
            export_frame, textvariable=self.save_dir, state="readonly"
        )
        self.save_dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # Add placeholder behavior
        self._update_save_dir_placeholder()

        # ========================================
        # ROW 2: Batch + Breaks (all on one line)
        # ========================================
        row2 = tk.Frame(inner, bg=Colors.BG)
        row2.pack(fill="x", pady=(0, 4))

        # Left side: Batch mode
        batch_frame = tk.Frame(row2, bg=Colors.BG)
        batch_frame.pack(side="left")

        self.batch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            batch_frame,
            text="Batch mode",
            variable=self.batch_var,
            command=self.toggle_batch,
        ).pack(side="left")

        self.file_btn = tk.Button(
            batch_frame,
            text="Select File",
            command=self.select_file,
            state="disabled",
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT_SECONDARY,
            font=("Segoe UI", 8),
            relief="flat",
            bd=1,
            cursor="hand2",
            padx=6,
        )
        self.file_btn.pack(side="left", padx=(8, 0))

        # Separator
        tk.Frame(row2, bg=Colors.BORDER, width=1).pack(
            side="left", fill="y", padx=15, pady=2
        )

        # Right side: Break settings
        break_frame = tk.Frame(row2, bg=Colors.BG)
        break_frame.pack(side="left")

        self.enable_breaks_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            break_frame,
            text="Breaks every",
            variable=self.enable_breaks_var,
            command=self.toggle_break_settings,
        ).pack(side="left")

        self.tweet_interval_var = tk.StringVar(value="100")
        self.tweet_interval_spin = ttk.Spinbox(
            break_frame,
            from_=50,
            to=500,
            increment=50,
            textvariable=self.tweet_interval_var,
            width=4,
            state="disabled",
        )
        self.tweet_interval_spin.pack(side="left", padx=(4, 2))

        tk.Label(
            break_frame,
            text="tweets,",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left")

        self.min_break_var = tk.StringVar(value="5")
        self.min_break_spin = ttk.Spinbox(
            break_frame,
            from_=1,
            to=30,
            textvariable=self.min_break_var,
            width=3,
            state="disabled",
        )
        self.min_break_spin.pack(side="left", padx=(4, 1))

        tk.Label(
            break_frame,
            text="-",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left")

        self.max_break_var = tk.StringVar(value="10")
        self.max_break_spin = ttk.Spinbox(
            break_frame,
            from_=1,
            to=30,
            textvariable=self.max_break_var,
            width=3,
            state="disabled",
        )
        self.max_break_spin.pack(side="left", padx=(1, 2))

        tk.Label(
            break_frame,
            text="min",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
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

        # Date preset dropdown
        if FEATURES_AVAILABLE:
            self.date_preset_var = tk.StringVar(value="Custom")
            preset_options = ["Custom"] + [p[0] for p in get_date_presets()]
            preset_combo = ttk.Combobox(
                date_frame,
                textvariable=self.date_preset_var,
                values=preset_options,
                state="readonly",
                width=10,
            )
            preset_combo.pack(side="left", padx=(0, 8))
            preset_combo.bind("<<ComboboxSelected>>", self._on_date_preset_selected)

        tk.Label(
            date_frame,
            text="From",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="left")

        self.start_entry = ttk.Entry(date_frame, width=11)
        self.start_entry.pack(side="left", padx=(5, 5))

        self.start_time_entry = ttk.Entry(date_frame, width=8)
        self.start_time_entry.pack(side="left", padx=(0, 10))
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

        self.end_entry = ttk.Entry(date_frame, width=11)
        self.end_entry.pack(side="left", padx=(5, 5))

        self.end_time_entry = ttk.Entry(date_frame, width=8)
        self.end_time_entry.pack(side="left")
        self.end_time_entry.insert(0, "23:59:59")
        self.end_time_entry.config(foreground="gray")
        self.end_time_entry.bind(
            "<FocusIn>", lambda e: self._on_time_focus_in(e, "23:59:59")
        )
        self.end_time_entry.bind("<FocusOut>", lambda e: self._validate_time_entry(e))

        # Row 3: Filters and format hint
        row3 = tk.Frame(inner, bg=Colors.BG)
        row3.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 0))

        tk.Label(
            row3,
            text="Format: YYYY-MM-DD",
            font=("Segoe UI", 8),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="left")

        # Filters button
        if FEATURES_AVAILABLE:
            self.filter_btn = tk.Button(
                row3,
                text="🔍 Filters",
                command=self.show_filter_dialog,
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT,
                font=("Segoe UI", 8),
                relief="flat",
                bd=1,
                cursor="hand2",
                padx=6,
            )
            self.filter_btn.pack(side="right", padx=(0, 5))

            # Cost estimate button
            self.cost_btn = tk.Button(
                row3,
                text="💰 Est. Cost",
                command=self.show_cost_estimate,
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT,
                font=("Segoe UI", 8),
                relief="flat",
                bd=1,
                cursor="hand2",
                padx=6,
            )
            self.cost_btn.pack(side="right", padx=(0, 5))

            # History button
            self.history_btn = tk.Button(
                row3,
                text="📜 History",
                command=self.show_history_dialog,
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT,
                font=("Segoe UI", 8),
                relief="flat",
                bd=1,
                cursor="hand2",
                padx=6,
            )
            self.history_btn.pack(side="right", padx=(0, 5))

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
            fg=Colors.TEXT,
            relief="flat",
            wrap=tk.WORD,
            height=10,
            insertbackground=Colors.TEXT,
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
            fg=Colors.TEXT,
            relief="flat",
            wrap=tk.WORD,
            height=10,
            insertbackground=Colors.TEXT,
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

    # ========================================
    # API METHODS
    # ========================================
    def _build_scraping_method_options(self):
        """Build list of scraping method options for dropdown."""
        options = [
            ("🍪 Cookie-based (Free)", "cookie"),
        ]

        if API_MODULE_AVAILABLE:
            # Add available API providers
            for provider in get_available_providers():
                info = get_provider_info(provider)
                display = f"🔑 {info['name']} ({info['pricing_display']})"
                options.append((display, provider.value))

            # Add coming soon providers (disabled)
            for provider in APIProviderType:
                if not is_provider_available(provider):
                    info = get_provider_info(provider)
                    display = f"⏳ {info['name']} (Coming Soon)"
                    options.append((display, f"_{provider.value}_disabled"))

        return options

    def _on_method_changed(self, event=None):
        """Handle scraping method selection change."""
        selected = self.method_var.get()
        method_value = self.method_display_map.get(selected, "cookie")

        # Check if disabled option selected
        if method_value.startswith("_") and method_value.endswith("_disabled"):
            messagebox.showinfo(
                "Coming Soon",
                "This API provider is not yet implemented.\n\n"
                "It will be available in a future update.",
            )
            # Reset to cookie-based
            self.method_var.set(self.method_options[0][0])
            method_value = "cookie"

        # Check if API key is configured
        if method_value != "cookie" and API_MODULE_AVAILABLE:
            api_key = get_api_key(method_value)
            if not api_key:
                result = messagebox.askyesno(
                    "API Key Required",
                    f"No API key configured for this provider.\n\n"
                    f"Would you like to add one now?",
                )
                if result:
                    self.show_api_key_dialog()
                else:
                    # Reset to cookie-based
                    self.method_var.set(self.method_options[0][0])
                    method_value = "cookie"

        self.scraping_method.set(method_value)
        self._update_api_status()
        self._update_cookie_section_visibility()
        self._update_config_button()

    def _update_api_status(self):
        """Update API status indicator."""
        if not hasattr(self, "api_status_lbl"):
            return

        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )

        if method == "cookie":
            self.api_status_lbl.config(text="", fg=Colors.TEXT_SECONDARY)
        elif API_MODULE_AVAILABLE:
            api_key = get_api_key(method)
            if api_key:
                self.api_status_lbl.config(text="✓ Key configured", fg=Colors.SUCCESS)
            else:
                self.api_status_lbl.config(text="⚠ No key", fg=Colors.WARNING)
        else:
            self.api_status_lbl.config(text="", fg=Colors.TEXT_SECONDARY)

    def _update_cookie_section_visibility(self):
        """Show/hide cookie section based on scraping method."""
        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )

        # Cookie section is only relevant for cookie-based scraping
        if hasattr(self, "cookie_toggle_btn"):
            if method == "cookie":
                self.cookie_toggle_btn.config(state="normal", fg=Colors.PRIMARY)
            else:
                self.cookie_toggle_btn.config(
                    state="disabled", fg=Colors.TEXT_SECONDARY
                )
                # Collapse if expanded
                if hasattr(self, "cookie_expanded") and self.cookie_expanded.get():
                    self.toggle_cookie_section()

    def _update_config_button(self):
        """Update config button icon based on selected method (🍪 or ⚙)."""
        if not hasattr(self, "config_btn"):
            return

        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )

        if method == "cookie":
            self.config_btn.config(text="🍪")
        else:
            self.config_btn.config(text="⚙")

    def _on_config_btn_click(self):
        """Handle config button click - opens appropriate dialog based on method."""
        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )

        if method == "cookie":
            self.show_cookie_dialog()
        else:
            self.show_api_key_dialog()

    def _update_save_dir_placeholder(self):
        """Update save directory display with placeholder if empty."""
        if not self.save_dir.get():
            # Create default exports folder
            default_dir = os.path.join(
                os.path.dirname(__file__), "..", "data", "exports"
            )
            os.makedirs(default_dir, exist_ok=True)
            self.save_dir.set(os.path.abspath(default_dir))

    def show_cookie_dialog(self):
        """Show cookie input dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Update Cookies")
        dialog.geometry("550x350")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=Colors.BG)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 275
        y = (dialog.winfo_screenheight() // 2) - 175
        dialog.geometry(f"550x350+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=20, pady=15)
        main.pack(fill="both", expand=True)

        # Header
        tk.Label(
            main,
            text="🍪 Update Cookies",
            font=("Segoe UI", 12, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(anchor="w", pady=(0, 10))

        # Instructions
        tk.Label(
            main,
            text="Paste your cookie JSON from Cookie-Editor extension:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 5))

        # Text area for cookies
        cookie_frame = tk.Frame(main, bg=Colors.BG)
        cookie_frame.pack(fill="both", expand=True, pady=(0, 10))

        cookie_text = tk.Text(
            cookie_frame,
            height=10,
            font=("Consolas", 9),
            bg=Colors.BG_SECONDARY,
            relief="solid",
            bd=1,
        )
        cookie_text.pack(fill="both", expand=True)

        # Help link
        help_frame = tk.Frame(main, bg=Colors.BG)
        help_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            help_frame,
            text="Need help?",
            font=("Segoe UI", 8),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="left")

        help_link = tk.Label(
            help_frame,
            text="Watch tutorial",
            font=("Segoe UI", 8, "underline"),
            bg=Colors.BG,
            fg=Colors.PRIMARY,
            cursor="hand2",
        )
        help_link.pack(side="left", padx=(5, 0))
        help_link.bind(
            "<Button-1>", lambda e: webbrowser.open("https://youtu.be/RKX2sgQVgBg")
        )

        # Buttons
        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x")

        def save_cookies():
            raw = cookie_text.get("1.0", tk.END).strip()
            if not raw:
                messagebox.showwarning("Empty", "Paste cookie JSON first.")
                return
            if convert_editthiscookie_to_twikit_format(raw):
                self.log("✓ Cookies saved")
                messagebox.showinfo("Success", "Cookies saved successfully!")
                dialog.destroy()
            else:
                messagebox.showerror(
                    "Error",
                    "Invalid cookie format.\n\nMake sure to export as JSON from Cookie-Editor.",
                )

        tk.Button(
            btn_frame,
            text="Save Cookies",
            command=save_cookies,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right")

        tk.Button(
            btn_frame,
            text="Cancel",
            command=dialog.destroy,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="right", padx=(0, 8))

    def _is_using_api(self):
        """Check if currently using API-based scraping."""
        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )
        return method != "cookie"

    def _get_api_scraper(self):
        """Get configured API scraper instance."""
        if not API_MODULE_AVAILABLE:
            return None

        method = self.scraping_method.get()
        if method == "cookie":
            return None

        api_key = get_api_key(method)
        if not api_key:
            return None

        try:
            provider = APIProviderType(method)
            return get_scraper(provider, api_key=api_key)
        except Exception as e:
            self.log(f"❌ Failed to create API scraper: {e}")
            return None

    def show_api_key_dialog(self):
        """Show API key management dialog."""
        if not API_MODULE_AVAILABLE:
            messagebox.showinfo(
                "API Module Not Available",
                "The API module is not installed.\n\n"
                "Please ensure the src/api and src/config folders are present.",
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("API Key Management")
        dialog.geometry("550x400")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=Colors.BG)

        try:
            icon_path = resource_path(os.path.join("assets", "logo.ico"))
            if os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except:
            pass

        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 275
        y = (dialog.winfo_screenheight() // 2) - 200
        dialog.geometry(f"550x400+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=20, pady=15)
        main.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(main, bg=Colors.PRIMARY, height=45)
        header.pack(fill="x", pady=(0, 15))
        header.pack_propagate(False)
        tk.Label(
            header,
            text="🔑 API Key Management",
            font=("Segoe UI", 12, "bold"),
            bg=Colors.PRIMARY,
            fg="white",
        ).pack(pady=10)

        # Instructions
        tk.Label(
            main,
            text="Configure API keys for different providers. Keys are stored locally and never shared.",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
            wraplength=500,
        ).pack(anchor="w", pady=(0, 15))

        # API Key entries frame
        keys_frame = tk.Frame(main, bg=Colors.BG)
        keys_frame.pack(fill="x", expand=False)

        # Store entry widgets for saving
        self._api_key_entries = {}

        manager = get_api_key_manager()
        status = manager.get_all_status()

        row = 0
        for provider in get_available_providers():
            info = get_provider_info(provider)
            provider_key = provider.value
            provider_status = status.get(provider_key, {})

            # Provider frame
            prov_frame = tk.Frame(keys_frame, bg=Colors.BG_SECONDARY, padx=10, pady=8)
            prov_frame.pack(fill="x", pady=(0, 10))

            # Top row: Name and pricing
            top_row = tk.Frame(prov_frame, bg=Colors.BG_SECONDARY)
            top_row.pack(fill="x")

            tk.Label(
                top_row,
                text=info["name"],
                font=("Segoe UI", 10, "bold"),
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT,
            ).pack(side="left")

            tk.Label(
                top_row,
                text=f"  •  {info['pricing_display']}",
                font=("Segoe UI", 9),
                bg=Colors.BG_SECONDARY,
                fg=Colors.TEXT_SECONDARY,
            ).pack(side="left")

            # Signup link
            signup_url = info.get("signup_url") or info.get("website", "")
            if signup_url:

                def make_open_link(url):
                    return lambda e: webbrowser.open(url)

                link_lbl = tk.Label(
                    top_row,
                    text="Get API Key →",
                    font=("Segoe UI", 8, "underline"),
                    bg=Colors.BG_SECONDARY,
                    fg=Colors.PRIMARY,
                    cursor="hand2",
                )
                link_lbl.pack(side="left", padx=(10, 0))
                link_lbl.bind("<Button-1>", make_open_link(signup_url))

            # Status indicator
            if provider_status.get("configured"):
                status_text = "✓ Configured"
                status_color = Colors.SUCCESS
            else:
                status_text = "Not configured"
                status_color = Colors.TEXT_SECONDARY

            tk.Label(
                top_row,
                text=status_text,
                font=("Segoe UI", 9),
                bg=Colors.BG_SECONDARY,
                fg=status_color,
            ).pack(side="right")

            # Bottom row: Key entry
            bottom_row = tk.Frame(prov_frame, bg=Colors.BG_SECONDARY)
            bottom_row.pack(fill="x", pady=(8, 0))
            bottom_row.columnconfigure(0, weight=1)

            key_entry = ttk.Entry(bottom_row, show="•", width=50)
            key_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

            # Pre-fill with existing key if any
            existing_key = manager.get_key(provider_key)
            if existing_key:
                key_entry.insert(0, existing_key)

            self._api_key_entries[provider_key] = key_entry

            # Show/Hide button
            show_var = tk.BooleanVar(value=False)

            def make_toggle(entry, var):
                def toggle():
                    if var.get():
                        entry.config(show="")
                    else:
                        entry.config(show="•")

                return toggle

            show_btn = ttk.Checkbutton(
                bottom_row,
                text="Show",
                variable=show_var,
                command=make_toggle(key_entry, show_var),
            )
            show_btn.grid(row=0, column=1, padx=(0, 5))

            # Test button
            def make_test(prov_key, entry):
                def test():
                    key = entry.get().strip()
                    if not key:
                        messagebox.showwarning(
                            "No Key", "Please enter an API key first."
                        )
                        return

                    # Show testing message
                    self.root.config(cursor="wait")
                    dialog.config(cursor="wait")
                    dialog.update()

                    try:
                        success, message = test_api_key(APIProviderType(prov_key), key)
                        if success:
                            messagebox.showinfo("Success", f"✓ {message}")
                        else:
                            messagebox.showerror("Failed", f"✗ {message}")
                    except Exception as e:
                        messagebox.showerror("Error", f"Test failed: {e}")
                    finally:
                        self.root.config(cursor="")
                        dialog.config(cursor="")

                return test

            test_btn = tk.Button(
                bottom_row,
                text="Test",
                command=make_test(provider_key, key_entry),
                bg=Colors.BG,
                fg=Colors.PRIMARY,
                font=("Segoe UI", 8),
                relief="flat",
                bd=1,
                cursor="hand2",
                padx=8,
            )
            test_btn.grid(row=0, column=2)

            row += 1

        # Coming soon providers
        for provider in APIProviderType:
            if not is_provider_available(provider):
                info = get_provider_info(provider)

                prov_frame = tk.Frame(
                    keys_frame, bg=Colors.BG_SECONDARY, padx=10, pady=8
                )
                prov_frame.pack(fill="x", pady=(0, 10))

                tk.Label(
                    prov_frame,
                    text=f"{info['name']}  •  {info['pricing_display']}",
                    font=("Segoe UI", 9),
                    bg=Colors.BG_SECONDARY,
                    fg=Colors.TEXT_SECONDARY,
                ).pack(side="left")

                tk.Label(
                    prov_frame,
                    text="Coming Soon",
                    font=("Segoe UI", 9, "italic"),
                    bg=Colors.BG_SECONDARY,
                    fg=Colors.TEXT_SECONDARY,
                ).pack(side="right")

        # Buttons
        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(15, 0))

        def save_keys():
            manager = get_api_key_manager()
            saved = 0
            for provider_key, entry in self._api_key_entries.items():
                key = entry.get().strip()
                if key:
                    set_api_key(provider_key, key, enabled=True)
                    saved += 1
                else:
                    # Clear key if empty
                    set_api_key(provider_key, "", enabled=False)

            self._update_api_status()
            messagebox.showinfo("Saved", f"API keys saved successfully.")
            dialog.destroy()

        tk.Button(
            btn_frame,
            text="Save",
            command=save_keys,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_frame,
            text="Cancel",
            command=dialog.destroy,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="right")

    # ========================================
    # FEATURE DIALOGS
    # ========================================

    def _on_date_preset_selected(self, event=None):
        """Handle date preset selection."""
        if not FEATURES_AVAILABLE:
            return

        preset_name = self.date_preset_var.get()
        if preset_name == "Custom":
            return

        presets = get_date_presets()
        for name, start, end in presets:
            if name == preset_name:
                self.start_entry.delete(0, tk.END)
                self.start_entry.insert(0, start)
                self.end_entry.delete(0, tk.END)
                self.end_entry.insert(0, end)
                break

    def show_cost_estimate(self):
        """Show estimated cost dialog."""
        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )

        # Calculate date range days
        try:
            start = self.start_entry.get().strip()
            end = self.end_entry.get().strip()
            if start and end:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                end_dt = datetime.strptime(end, "%Y-%m-%d")
                days = (end_dt - start_dt).days + 1
            else:
                days = 30
        except:
            days = 30

        # Rough estimate: 5-20 tweets per day depending on user
        est_low = days * 5
        est_high = days * 20
        est_mid = days * 10

        if method == "cookie":
            cost_str = "Free (Cookie-based)"
            detail = "Cookie-based scraping has no direct cost."
        else:
            cost_low = estimate_cost(method, est_low) if FEATURES_AVAILABLE else 0
            cost_high = estimate_cost(method, est_high) if FEATURES_AVAILABLE else 0
            cost_mid = estimate_cost(method, est_mid) if FEATURES_AVAILABLE else 0
            cost_str = f"${cost_low:.2f} - ${cost_high:.2f}"
            detail = (
                f"Based on {days} days, estimating {est_low:,} - {est_high:,} tweets"
            )

        messagebox.showinfo(
            "Cost Estimate",
            f"📊 Estimated Cost\n\n"
            f"Method: {method}\n"
            f"Date range: {days} days\n\n"
            f"Estimated tweets: {est_low:,} - {est_high:,}\n"
            f"Estimated cost: {cost_str}\n\n"
            f"Note: Actual results vary by account activity.",
        )

    def show_filter_dialog(self):
        """Show filter settings dialog."""
        if not FEATURES_AVAILABLE:
            messagebox.showinfo("Filters", "Filter feature not available.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Filter Settings")
        dialog.geometry("400x350")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=Colors.BG)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 200
        y = (dialog.winfo_screenheight() // 2) - 175
        dialog.geometry(f"400x350+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=20, pady=15)
        main.pack(fill="both", expand=True)

        # Header
        tk.Label(
            main,
            text="🔍 Filter Settings",
            font=("Segoe UI", 12, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(anchor="w", pady=(0, 15))

        tk.Label(
            main,
            text="Filter tweets during scraping:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 10))

        # Engagement filters
        eng_frame = tk.LabelFrame(
            main,
            text="Engagement Filters",
            bg=Colors.BG,
            fg=Colors.TEXT,
            padx=10,
            pady=10,
        )
        eng_frame.pack(fill="x", pady=(0, 10))

        # Min likes
        likes_row = tk.Frame(eng_frame, bg=Colors.BG)
        likes_row.pack(fill="x", pady=2)
        tk.Label(
            likes_row,
            text="Min likes:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
            width=12,
            anchor="w",
        ).pack(side="left")
        self._filter_min_likes = tk.StringVar(value=str(self.filters.min_likes))
        ttk.Spinbox(
            likes_row, from_=0, to=100000, textvariable=self._filter_min_likes, width=10
        ).pack(side="left")

        # Min retweets
        rt_row = tk.Frame(eng_frame, bg=Colors.BG)
        rt_row.pack(fill="x", pady=2)
        tk.Label(
            rt_row,
            text="Min retweets:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
            width=12,
            anchor="w",
        ).pack(side="left")
        self._filter_min_rt = tk.StringVar(value=str(self.filters.min_retweets))
        ttk.Spinbox(
            rt_row, from_=0, to=100000, textvariable=self._filter_min_rt, width=10
        ).pack(side="left")

        # Content filters
        content_frame = tk.LabelFrame(
            main, text="Content Filters", bg=Colors.BG, fg=Colors.TEXT, padx=10, pady=10
        )
        content_frame.pack(fill="x", pady=(0, 10))

        self._filter_excl_rt = tk.BooleanVar(value=self.filters.exclude_retweets)
        ttk.Checkbutton(
            content_frame, text="Exclude retweets", variable=self._filter_excl_rt
        ).pack(anchor="w")

        self._filter_excl_replies = tk.BooleanVar(value=self.filters.exclude_replies)
        ttk.Checkbutton(
            content_frame, text="Exclude replies", variable=self._filter_excl_replies
        ).pack(anchor="w")

        self._filter_media = tk.BooleanVar(value=self.filters.media_only)
        ttk.Checkbutton(
            content_frame,
            text="Media only (tweets with images/video)",
            variable=self._filter_media,
        ).pack(anchor="w")

        # Buttons
        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(15, 0))

        def save_filters():
            try:
                self.filters.min_likes = int(self._filter_min_likes.get())
                self.filters.min_retweets = int(self._filter_min_rt.get())
            except:
                pass
            self.filters.exclude_retweets = self._filter_excl_rt.get()
            self.filters.exclude_replies = self._filter_excl_replies.get()
            self.filters.media_only = self._filter_media.get()

            # Save to settings
            if self.settings_manager:
                self.settings_manager.update(
                    min_likes=self.filters.min_likes,
                    min_retweets=self.filters.min_retweets,
                    exclude_retweets=self.filters.exclude_retweets,
                    exclude_replies=self.filters.exclude_replies,
                    media_only=self.filters.media_only,
                )

            dialog.destroy()
            messagebox.showinfo("Saved", "Filter settings saved.")

        tk.Button(
            btn_frame,
            text="Save",
            command=save_filters,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right")

        tk.Button(
            btn_frame,
            text="Cancel",
            command=dialog.destroy,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="right", padx=(0, 8))

    def show_history_dialog(self):
        """Show scrape history dialog."""
        if not FEATURES_AVAILABLE or not self.history_manager:
            messagebox.showinfo("History", "History feature not available.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Scrape History")
        dialog.geometry("700x450")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=Colors.BG)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 350
        y = (dialog.winfo_screenheight() // 2) - 225
        dialog.geometry(f"700x450+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=15, pady=10)
        main.pack(fill="both", expand=True)

        # Header with stats
        header = tk.Frame(main, bg=Colors.BG)
        header.pack(fill="x", pady=(0, 10))

        tk.Label(
            header,
            text="📜 Scrape History",
            font=("Segoe UI", 12, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left")

        stats = self.history_manager.get_total_stats()
        tk.Label(
            header,
            text=f"Total: {stats['total_scrapes']} scrapes | {stats['total_tweets']:,} tweets | ${stats['total_cost']:.2f}",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="right")

        # Treeview for history
        tree_frame = tk.Frame(main, bg=Colors.BG)
        tree_frame.pack(fill="both", expand=True)

        columns = ("date", "target", "tweets", "method", "cost", "status")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        tree.heading("date", text="Date")
        tree.heading("target", text="Target")
        tree.heading("tweets", text="Tweets")
        tree.heading("method", text="Method")
        tree.heading("cost", text="Cost")
        tree.heading("status", text="Status")

        tree.column("date", width=130)
        tree.column("target", width=200)
        tree.column("tweets", width=70)
        tree.column("method", width=80)
        tree.column("cost", width=60)
        tree.column("status", width=80)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Populate history
        for record in self.history_manager.get_recent(50):
            cost_str = f"${record.cost:.2f}" if record.cost > 0 else "Free"
            tree.insert(
                "",
                "end",
                values=(
                    record.timestamp,
                    (
                        record.target[:30] + "..."
                        if len(record.target) > 30
                        else record.target
                    ),
                    f"{record.tweet_count:,}",
                    record.method,
                    cost_str,
                    record.status,
                ),
            )

        # Buttons
        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(10, 0))

        def clear_history():
            if messagebox.askyesno(
                "Clear History", "Are you sure you want to clear all history?"
            ):
                self.history_manager.clear()
                for item in tree.get_children():
                    tree.delete(item)

        def open_file():
            selected = tree.selection()
            if selected:
                idx = tree.index(selected[0])
                record = self.history_manager.get_recent(50)[idx]
                if record.output_file and os.path.exists(record.output_file):
                    folder = os.path.dirname(record.output_file)
                    # Cross-platform folder open
                    if sys.platform == "win32":
                        os.startfile(folder)
                    elif sys.platform == "darwin":  # macOS
                        import subprocess

                        subprocess.run(["open", folder])
                    else:  # Linux
                        import subprocess

                        subprocess.run(["xdg-open", folder])

        tk.Button(
            btn_frame,
            text="📂 Open Folder",
            command=open_file,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=5,
        ).pack(side="left")

        tk.Button(
            btn_frame,
            text="🗑 Clear All",
            command=clear_history,
            bg=Colors.BG_SECONDARY,
            fg=Colors.ERROR,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=5,
        ).pack(side="left", padx=(8, 0))

        tk.Button(
            btn_frame,
            text="Close",
            command=dialog.destroy,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=5,
        ).pack(side="right")

    def show_preview_dialog(self, tweets: list, on_confirm):
        """Show preview of scraped tweets before saving."""
        if not tweets:
            messagebox.showinfo("Preview", "No tweets to preview.")
            on_confirm()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Preview - {len(tweets)} tweets")
        dialog.geometry("800x500")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=Colors.BG)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 400
        y = (dialog.winfo_screenheight() // 2) - 250
        dialog.geometry(f"800x500+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=15, pady=10)
        main.pack(fill="both", expand=True)

        # Header
        tk.Label(
            main,
            text=f"📋 Preview ({len(tweets)} tweets)",
            font=("Segoe UI", 12, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(anchor="w", pady=(0, 10))

        # Treeview
        tree_frame = tk.Frame(main, bg=Colors.BG)
        tree_frame.pack(fill="both", expand=True)

        columns = ("date", "user", "text", "likes", "rt")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        tree.heading("date", text="Date")
        tree.heading("user", text="User")
        tree.heading("text", text="Text")
        tree.heading("likes", text="Likes")
        tree.heading("rt", text="RT")

        tree.column("date", width=120)
        tree.column("user", width=100)
        tree.column("text", width=400)
        tree.column("likes", width=60)
        tree.column("rt", width=60)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Show first 100 tweets
        for tweet in tweets[:100]:
            if isinstance(tweet, dict):
                date = tweet.get("date", "")[:16]
                user = tweet.get("username", "")[:15]
                text = tweet.get("text", "")[:80].replace("\n", " ")
                likes = tweet.get("likes", 0)
                rt = tweet.get("retweets", 0)
            else:
                date = getattr(tweet, "date", "")[:16]
                user = getattr(tweet, "username", "")[:15]
                text = getattr(tweet, "text", "")[:80].replace("\n", " ")
                likes = getattr(tweet, "likes", 0)
                rt = getattr(tweet, "retweets", 0)

            tree.insert("", "end", values=(date, user, text, likes, rt))

        if len(tweets) > 100:
            tree.insert(
                "",
                "end",
                values=("...", "...", f"+ {len(tweets) - 100} more tweets", "", ""),
            )

        # Buttons
        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(10, 0))

        def confirm():
            dialog.destroy()
            on_confirm()

        def cancel():
            dialog.destroy()

        tk.Button(
            btn_frame,
            text="💾 Save",
            command=confirm,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(side="right")

        tk.Button(
            btn_frame,
            text="Cancel",
            command=cancel,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="right", padx=(0, 8))

    def show_analytics_dialog(self, tweets: list):
        """Show analytics after scrape completion."""
        if not FEATURES_AVAILABLE or not tweets:
            return

        # Convert to dicts if needed
        tweet_dicts = []
        for t in tweets:
            if isinstance(t, dict):
                tweet_dicts.append(t)
            else:
                tweet_dicts.append(t.to_dict() if hasattr(t, "to_dict") else vars(t))

        analytics = calculate_analytics(tweet_dicts)
        summary = format_analytics_summary(analytics)

        dialog = tk.Toplevel(self.root)
        dialog.title("Scrape Analytics")
        dialog.geometry("450x550")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.configure(bg=Colors.BG)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 225
        y = (dialog.winfo_screenheight() // 2) - 275
        dialog.geometry(f"450x550+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=20, pady=15)
        main.pack(fill="both", expand=True)

        # Text area with analytics
        text = tk.Text(
            main,
            font=("Consolas", 10),
            bg=Colors.BG_SECONDARY,
            relief="flat",
            wrap=tk.WORD,
            padx=15,
            pady=10,
        )
        text.pack(fill="both", expand=True)
        text.insert("1.0", summary)
        text.config(state="disabled")

        # Close button
        tk.Button(
            main,
            text="Close",
            command=dialog.destroy,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
        ).pack(pady=(10, 0))

    def show_queue_dialog(self):
        """Show queue management dialog for batch scraping."""
        if not FEATURES_AVAILABLE:
            messagebox.showinfo("Queue", "Queue feature not available.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Scrape Queue")
        dialog.geometry("500x400")
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.configure(bg=Colors.BG)

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - 250
        y = (dialog.winfo_screenheight() // 2) - 200
        dialog.geometry(f"500x400+{x}+{y}")

        main = tk.Frame(dialog, bg=Colors.BG, padx=15, pady=10)
        main.pack(fill="both", expand=True)

        # Header
        tk.Label(
            main,
            text="📋 Scrape Queue",
            font=("Segoe UI", 12, "bold"),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(anchor="w", pady=(0, 10))

        # Add username input
        add_frame = tk.Frame(main, bg=Colors.BG)
        add_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            add_frame,
            text="Add username:",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT,
        ).pack(side="left")
        username_entry = ttk.Entry(add_frame, width=25)
        username_entry.pack(side="left", padx=(8, 8))

        def add_to_queue():
            username = username_entry.get().strip().lstrip("@")
            if username:
                self.scrape_queue.add(username)
                refresh_list()
                username_entry.delete(0, tk.END)

        tk.Button(
            add_frame,
            text="Add",
            command=add_to_queue,
            bg=Colors.PRIMARY,
            fg="white",
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            padx=10,
        ).pack(side="left")

        # Load from file button
        def load_from_file():
            file_path = filedialog.askopenfilename(
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if file_path:
                with open(file_path, "r", encoding="utf-8") as f:
                    usernames = [
                        u.strip().lstrip("@")
                        for u in f.read().replace("\n", ",").split(",")
                        if u.strip()
                    ]
                    self.scrape_queue.add_multiple(usernames)
                    refresh_list()

        tk.Button(
            add_frame,
            text="📂 Load File",
            command=load_from_file,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            padx=8,
        ).pack(side="left", padx=(8, 0))

        # Queue list
        list_frame = tk.Frame(main, bg=Colors.BG)
        list_frame.pack(fill="both", expand=True)

        columns = ("username", "status", "tweets")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)

        tree.heading("username", text="Username")
        tree.heading("status", text="Status")
        tree.heading("tweets", text="Tweets")

        tree.column("username", width=200)
        tree.column("status", width=100)
        tree.column("tweets", width=80)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def refresh_list():
            for item in tree.get_children():
                tree.delete(item)
            for item in self.scrape_queue.items:
                status_emoji = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "error": "❌",
                }.get(item.status, "")
                tree.insert(
                    "",
                    "end",
                    values=(
                        f"@{item.username}",
                        f"{status_emoji} {item.status}",
                        str(item.tweet_count) if item.tweet_count else "-",
                    ),
                )

        refresh_list()

        # Buttons
        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(10, 0))

        def remove_selected():
            selected = tree.selection()
            if selected:
                for sel in selected:
                    username = tree.item(sel)["values"][0].lstrip("@")
                    self.scrape_queue.remove(username)
                refresh_list()

        def clear_queue():
            self.scrape_queue.clear()
            refresh_list()

        tk.Button(
            btn_frame,
            text="Remove Selected",
            command=remove_selected,
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            padx=8,
        ).pack(side="left")

        tk.Button(
            btn_frame,
            text="Clear All",
            command=clear_queue,
            bg=Colors.BG_SECONDARY,
            fg=Colors.ERROR,
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            padx=8,
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            btn_frame,
            text=f"Queue: {len(self.scrape_queue.items)} users",
            font=("Segoe UI", 9),
            bg=Colors.BG,
            fg=Colors.TEXT_SECONDARY,
        ).pack(side="right")

    def _load_last_settings(self):
        """Load and apply last used settings."""
        if not FEATURES_AVAILABLE or not self.settings_manager:
            return

        s = self.settings_manager.settings

        # Apply last values
        if s.last_username:
            self.username_entry.delete(0, tk.END)
            self.username_entry.insert(0, s.last_username)

        if s.last_keywords:
            self.keyword_entry.delete(0, tk.END)
            self.keyword_entry.insert(0, s.last_keywords)

        if s.last_mode:
            self.mode_var.set(s.last_mode)
            self.update_mode()

        if s.last_start_date:
            self.start_entry.delete(0, tk.END)
            self.start_entry.insert(0, s.last_start_date)

        if s.last_end_date:
            self.end_entry.delete(0, tk.END)
            self.end_entry.insert(0, s.last_end_date)

        if s.last_export_format:
            self.format_var.set(s.last_export_format)

        # Load filter settings
        if self.filters:
            self.filters.min_likes = s.min_likes
            self.filters.min_retweets = s.min_retweets
            self.filters.exclude_retweets = s.exclude_retweets
            self.filters.exclude_replies = s.exclude_replies
            self.filters.media_only = s.media_only

    def _save_current_settings(self):
        """Save current settings for next session."""
        if not FEATURES_AVAILABLE or not self.settings_manager:
            return

        self.settings_manager.update(
            last_username=self.username_entry.get().strip(),
            last_keywords=self.keyword_entry.get().strip(),
            last_mode=self.mode_var.get(),
            last_start_date=self.start_entry.get().strip(),
            last_end_date=self.end_entry.get().strip(),
            last_export_format=self.format_var.get(),
            last_scraping_method=(
                self.scraping_method.get()
                if hasattr(self, "scraping_method")
                else "cookie"
            ),
        )

    def _record_scrape_history(
        self,
        mode,
        target,
        tweet_count,
        start_date,
        end_date,
        output_file,
        status="completed",
    ):
        """Record a completed scrape in history."""
        if not FEATURES_AVAILABLE or not self.history_manager:
            return

        method = (
            self.scraping_method.get() if hasattr(self, "scraping_method") else "cookie"
        )
        cost = estimate_cost(method, tweet_count) if method != "cookie" else 0.0

        duration = 0
        if self._scrape_start_time:
            duration = int(time_module.time() - self._scrape_start_time)

        self.history_manager.create_record(
            mode=mode,
            target=target,
            tweet_count=tweet_count,
            start_date=start_date,
            end_date=end_date,
            method=method,
            cost=cost,
            output_file=output_file or "",
            duration_seconds=duration,
            status=status,
        )

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
                    resume_state = None
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
                                resume_state=resume_state,
                            )
                            self.state_manager.clear_state()
                            return out, cnt
                        except CookieExpiredError:
                            resume_state = self.state_manager.load_state()
                            action = self._wait_for_user_action(
                                "cookie",
                                "Cookies expired",
                                {
                                    "tweets_scraped": (
                                        resume_state.get("tweets_scraped", 0)
                                        if resume_state
                                        else 0
                                    )
                                },
                            )
                            if action == "stop":
                                return None, 0
                            retry += 1
                        except NetworkError as e:
                            resume_state = self.state_manager.load_state()
                            action = self._wait_for_user_action(
                                "network",
                                str(e),
                                {
                                    "tweets_scraped": (
                                        resume_state.get("tweets_scraped", 0)
                                        if resume_state
                                        else 0
                                    )
                                },
                            )
                            if action == "stop":
                                return None, 0
                            retry += 1
                        except Exception as e:
                            resume_state = self.state_manager.load_state()
                            action = self._wait_for_user_action(
                                "unknown",
                                str(e),
                                {
                                    "tweets_scraped": (
                                        resume_state.get("tweets_scraped", 0)
                                        if resume_state
                                        else 0
                                    )
                                },
                            )
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
                resume_state = None
                while retry < 5:
                    try:
                        out, cnt, failed, _ = await scrape_tweet_links_file(
                            file_path=path,
                            export_format=fmt,
                            save_dir=save_dir,
                            progress_callback=progress_cb,
                            should_stop_callback=self._should_stop,
                            break_settings=break_settings,
                            resume_state=resume_state,
                        )
                        self.state_manager.clear_state()
                        return out, cnt, failed
                    except CookieExpiredError:
                        resume_state = self.state_manager.load_state()
                        action = self._wait_for_user_action(
                            "cookie",
                            "Cookies expired",
                            {
                                "tweets_scraped": (
                                    resume_state.get("tweets_scraped", 0)
                                    if resume_state
                                    else 0
                                )
                            },
                        )
                        if action == "stop":
                            return None, 0, 0
                        retry += 1
                    except NetworkError as e:
                        resume_state = self.state_manager.load_state()
                        action = self._wait_for_user_action(
                            "network",
                            str(e),
                            {
                                "tweets_scraped": (
                                    resume_state.get("tweets_scraped", 0)
                                    if resume_state
                                    else 0
                                )
                            },
                        )
                        if action == "stop":
                            return None, 0, 0
                        retry += 1
                    except Exception as e:
                        resume_state = self.state_manager.load_state()
                        action = self._wait_for_user_action(
                            "unknown",
                            str(e),
                            {
                                "tweets_scraped": (
                                    resume_state.get("tweets_scraped", 0)
                                    if resume_state
                                    else 0
                                )
                            },
                        )
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
        self._stop_requested = False
        self._is_running = True

        # Check if using API or cookie-based scraping
        if self._is_using_api():
            scraper = self._get_api_scraper()
            if not scraper:
                messagebox.showerror(
                    "API Error",
                    "Could not initialize API scraper.\n\n"
                    "Please check your API key configuration.",
                )
                self._cleanup_after_scrape()
                return

            method_name = self.scraping_method.get()
            self.log(f"🔑 Starting API scrape ({method_name})...")
            threading.Thread(
                target=self._run_api_scrape,
                args=(scraper, target, start, end, fmt, save_dir, break_settings),
                daemon=True,
            ).start()
        else:
            self.log("🍪 Starting cookie-based scrape...")
            threading.Thread(
                target=self._run_scrape,
                args=(target, start, end, fmt, save_dir, break_settings),
                daemon=True,
            ).start()

    def _run_api_scrape(
        self, scraper, target, start, end, fmt, save_dir, break_settings
    ):
        """Run scraping using API provider instead of cookies."""

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

        try:
            # Determine max results (large number for API, it will paginate)
            max_results = 10000

            if target[0] == "batch":
                users = target[1]
                all_tweets = []

                for i, username in enumerate(users):
                    if self._should_stop():
                        progress_cb("🛑 Stop requested")
                        break

                    progress_cb(f"👤 User {i+1}/{len(users)}: @{username}")

                    try:
                        result = scraper.get_user_tweets(
                            username=username,
                            start_date=start,
                            end_date=end,
                            max_results=max_results,
                            exclude_replies=True,
                            progress_callback=progress_cb,
                            should_stop_callback=self._should_stop,
                        )

                        if result.success:
                            all_tweets.extend(result.tweets)
                            progress_cb(
                                f"✓ Got {len(result.tweets)} tweets for @{username}"
                            )
                            progress_cb(len(all_tweets))
                        else:
                            progress_cb(f"⚠️ Error for @{username}: {result.error}")

                    except APIAuthenticationError as e:
                        progress_cb(f"🔑 Auth error: {e}")
                        self._handle_api_auth_error()
                        break
                    except APIRateLimitError as e:
                        progress_cb(f"⏳ Rate limit hit. Waiting {e.retry_after}s...")
                        import time

                        time.sleep(e.retry_after)
                        continue
                    except Exception as e:
                        progress_cb(f"❌ Error: {e}")
                        continue

                # Save all tweets
                if all_tweets:
                    output_path = self._save_api_tweets(
                        all_tweets, "batch", fmt, save_dir
                    )
                    progress_cb(f"✅ Saved {len(all_tweets)} tweets to {output_path}")
                    stats = scraper.get_usage_stats()
                    progress_cb(f"💰 Estimated cost: ${stats['estimated_cost']:.4f}")
                    messagebox.showinfo(
                        "Complete",
                        f"Scraped {len(all_tweets)} tweets!\n\n"
                        f"API calls: {stats['total_api_calls']}\n"
                        f"Est. cost: ${stats['estimated_cost']:.4f}\n\n"
                        f"Saved to:\n{output_path}",
                    )
                else:
                    progress_cb("⚠️ No tweets collected")

            else:
                # Single user or keyword search
                _, user, kws = target

                if user:
                    progress_cb(f"👤 Scraping @{user}...")
                    result = scraper.get_user_tweets(
                        username=user,
                        start_date=start,
                        end_date=end,
                        max_results=max_results,
                        exclude_replies=True,
                        progress_callback=progress_cb,
                        should_stop_callback=self._should_stop,
                    )
                else:
                    use_and = self.op_var.get() == "AND"
                    progress_cb(
                        f"🔍 Searching: {', '.join(kws)} ({'AND' if use_and else 'OR'})..."
                    )
                    result = scraper.search_tweets(
                        keywords=kws,
                        start_date=start,
                        end_date=end,
                        max_results=max_results,
                        use_and=use_and,
                        exclude_replies=True,
                        progress_callback=progress_cb,
                        should_stop_callback=self._should_stop,
                    )

                if result.success and result.tweets:
                    name = user or "_".join(kws[:2])
                    output_path = self._save_api_tweets(
                        result.tweets, name, fmt, save_dir
                    )
                    progress_cb(f"✅ Saved {len(result.tweets)} tweets")
                    stats = scraper.get_usage_stats()
                    progress_cb(f"💰 Estimated cost: ${stats['estimated_cost']:.4f}")
                    messagebox.showinfo(
                        "Complete",
                        f"Scraped {len(result.tweets)} tweets!\n\n"
                        f"API calls: {stats['total_api_calls']}\n"
                        f"Est. cost: ${stats['estimated_cost']:.4f}\n\n"
                        f"Saved to:\n{output_path}",
                    )
                elif result.error:
                    progress_cb(f"❌ Error: {result.error}")
                    messagebox.showerror("Error", f"Scraping failed:\n{result.error}")
                else:
                    progress_cb("⚠️ No tweets found matching criteria")
                    messagebox.showinfo(
                        "Complete", "No tweets found matching your criteria."
                    )

        except APIAuthenticationError as e:
            self.log(f"🔑 Authentication failed: {e}")
            self._handle_api_auth_error()
        except APIRateLimitError as e:
            self.log(f"⏳ Rate limited: {e}")
            messagebox.showwarning(
                "Rate Limited",
                f"API rate limit exceeded.\n\nPlease wait {e.retry_after // 60} minutes and try again.",
            )
        except Exception as e:
            self.log(f"❌ Error: {e}")
            messagebox.showerror("Error", f"An error occurred:\n{e}")
        finally:
            self._cleanup_after_scrape()

    def _save_api_tweets(self, tweets, name, fmt, save_dir):
        """Save API-scraped tweets to file."""
        import pandas as pd
        from datetime import datetime as dt

        # Ensure save directory exists
        os.makedirs(save_dir, exist_ok=True)

        # Create filename
        timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        ext = "xlsx" if fmt == "excel" else "csv"
        filename = f"{safe_name}_{timestamp}_api.{ext}"
        output_path = os.path.join(save_dir, filename)

        # Convert tweets to dataframe
        data = [tweet.to_dict() for tweet in tweets]
        df = pd.DataFrame(data)

        # Reorder columns to match cookie-based output
        column_order = [
            "date",
            "username",
            "display_name",
            "text",
            "retweets",
            "likes",
            "replies",
            "quotes",
            "views",
            "tweet_id",
            "tweet_url",
        ]
        df = df[[c for c in column_order if c in df.columns]]

        # Save
        if fmt == "excel":
            df.to_excel(output_path, index=False, engine="openpyxl")
        else:
            df.to_csv(output_path, index=False, encoding="utf-8-sig")

        return output_path

    def _handle_api_auth_error(self):
        """Handle API authentication errors."""
        result = messagebox.askyesno(
            "Authentication Failed",
            "API authentication failed. Your API key may be invalid or expired.\n\n"
            "Would you like to update your API key now?",
        )
        if result:
            self.show_api_key_dialog()

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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Choose method: 🍪 Cookie (Free) or 🔑 API (Paid)
2. Click 🍪 or ⚙ to configure authentication
3. Enter username OR keywords
4. Set date range (use presets for quick selection)
5. Click "Start Scraping"


🔐 AUTHENTICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COOKIES (Free):
• Install "Cookie-Editor" browser extension
• Go to Twitter → Export cookies as JSON
• Click 🍪 → Paste → Save

API (Paid ~$0.14/1k tweets):
• Click ⚙ → Get API Key link
• Sign up at twexapi.io
• Paste key → Test → Save


⚠️ ANTIVIRUS WARNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
App may be flagged - this is a FALSE POSITIVE!

Windows Defender fix:
1. Windows Security → Virus protection
2. Manage settings → Exclusions
3. Add exclusion → Folder → Select app folder

📥 Download full documentation for detailed instructions.


📊 EXPORT FORMATS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Excel, CSV, JSON, SQLite, HTML, Markdown


🆘 COMMON ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Cookie expired → Get fresh cookies
• Rate limit → Wait 15 min or enable breaks
• No tweets → Check username/date range


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Made with ❤️ by OJ | v1.4.0 | Jan 2025
"""

        text_frame = tk.Frame(main, bg=Colors.BG)
        text_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        text = tk.Text(
            text_frame,
            font=("Consolas", 9),
            bg=Colors.BG_SECONDARY,
            fg=Colors.TEXT,  # Added text color
            relief="flat",
            wrap=tk.WORD,
            padx=15,
            pady=10,
            yscrollcommand=scrollbar.set,
            insertbackground=Colors.TEXT,  # Cursor color
        )
        text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text.yview)

        text.insert("1.0", help_text)
        text.config(state="disabled")

        btn_frame = tk.Frame(main, bg=Colors.BG)
        btn_frame.pack(fill="x", pady=(15, 0))

        # PDF Download button
        tk.Button(
            btn_frame,
            text="📥 Download Full Docs",
            command=self._download_documentation,
            bg=Colors.SUCCESS,
            fg="white",
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="left", padx=(0, 8))

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

    def _toggle_dark_mode(self):
        """Toggle dark mode and apply immediately."""
        # Toggle the state
        is_dark = not Colors.is_dark_mode()
        Colors.set_dark_mode(is_dark)

        # Update button icon
        if hasattr(self, "dark_mode_btn"):
            self.dark_mode_btn.config(text="☀️" if is_dark else "🌙")

        # Save preference
        if FEATURES_AVAILABLE and self.app_settings:
            self.app_settings.dark_mode = is_dark
            save_app_settings(self.app_settings)

        # Apply theme to entire app
        self._apply_theme()

    def _apply_theme(self):
        """Apply current theme colors to all widgets."""
        # Update root
        self.root.configure(bg=Colors.BG)

        # Recursively update all widgets
        self._update_widget_colors(self.root)

        # Update ttk styles
        self.setup_styles()

    def _update_widget_colors(self, widget):
        """Recursively update widget colors for theme change."""
        try:
            widget_class = widget.winfo_class()

            # Skip ttk widgets (handled by styles)
            if widget_class.startswith("T"):
                pass
            elif widget_class in ("Frame", "Labelframe"):
                widget.configure(bg=Colors.BG)
            elif widget_class == "Label":
                # Check if it's a header label (white text on primary)
                try:
                    current_bg = widget.cget("bg")
                    if (
                        current_bg == Colors.PRIMARY
                        or current_bg == "#2563eb"
                        or current_bg == "#3b82f6"
                    ):
                        widget.configure(bg=Colors.PRIMARY, fg="white")
                    else:
                        widget.configure(bg=Colors.BG, fg=Colors.TEXT)
                except:
                    pass
            elif widget_class == "Button":
                try:
                    current_bg = widget.cget("bg")
                    # Keep primary/success/error buttons as-is
                    if current_bg not in (
                        Colors.PRIMARY,
                        Colors.SUCCESS,
                        Colors.ERROR,
                        "#2563eb",
                        "#22c55e",
                        "#ef4444",
                        "#3b82f6",
                        "#4ade80",
                        "#f87171",
                    ):
                        widget.configure(bg=Colors.BG, fg=Colors.TEXT)
                except:
                    pass
            elif widget_class == "Text":
                widget.configure(bg=Colors.BG_SECONDARY, fg=Colors.TEXT)
            elif widget_class == "Entry":
                widget.configure(bg=Colors.BG_SECONDARY, fg=Colors.TEXT)
        except Exception:
            pass

        # Process children
        for child in widget.winfo_children():
            self._update_widget_colors(child)

    def _download_documentation(self):
        """Download full documentation as PDF file."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("Text files", "*.txt")],
            initialfile="Chi_Tweet_Scraper_Documentation.pdf",
            title="Save Documentation",
        )

        if not filepath:
            return

        # Documentation content
        doc_sections = [
            ("Chi Tweet Scraper", "Complete User Documentation - Version 1.4.0"),
            (
                "1. INTRODUCTION",
                """Chi Tweet Scraper is a professional desktop application for collecting data from Twitter/X. It supports both free (cookie-based) and paid (API-based) scraping methods.

Key capabilities:
• Scrape tweets by username or keywords
• Multiple export formats (Excel, CSV, JSON, SQLite, HTML, Markdown)
• Date range filtering with presets
• Engagement filters (min likes, retweets)
• Batch processing for multiple accounts
• Dark mode support
• Automatic retry on errors""",
            ),
            (
                "2. SYSTEM REQUIREMENTS",
                """• Operating System: Windows 10/11, macOS, or Linux
• Python: 3.8 or higher (if running from source)
• RAM: 4GB minimum, 8GB recommended
• Internet connection required
• Browser with Cookie-Editor extension (for cookie method)""",
            ),
            (
                "3. INSTALLATION",
                """Option A: From Executable (Windows)
1. Download the .exe file
2. Extract to a folder of your choice
3. IMPORTANT: Whitelist in antivirus (see Section 4)
4. Double-click to run

Option B: From Source (All Platforms)
1. Install Python 3.8+
2. Download/clone the source code
3. Run: pip install -r requirements.txt
4. Run: python -m src.gui""",
            ),
            (
                "4. ANTIVIRUS WHITELIST (IMPORTANT!)",
                """The application may be flagged by antivirus - THIS IS A FALSE POSITIVE.

Why it's flagged:
• Built with PyInstaller (used by both legitimate apps and malware)
• Makes network requests (to Twitter/APIs)
• Writes files to disk (exports)
• Not digitally signed (costs $200-300/year)

WINDOWS DEFENDER WHITELIST:
1. Open Windows Security (search in Start menu)
2. Click "Virus & threat protection"
3. Click "Manage settings" under Virus & threat protection settings
4. Scroll to "Exclusions" → "Add or remove exclusions"
5. Click "Add an exclusion" → "Folder"
6. Select the Chi Tweet Scraper folder

OTHER ANTIVIRUS:
• Norton: Settings → Antivirus → Scans and Risks → Items to Exclude
• McAfee: Settings → Real-Time Scanning → Excluded Files
• Avast: Menu → Settings → General → Exceptions
• Bitdefender: Protection → Settings → Exclusions""",
            ),
            (
                "5. COOKIE AUTHENTICATION (Free)",
                """This method uses your Twitter login cookies.

Setup steps:
1. Install "Cookie-Editor" browser extension (Chrome/Firefox/Edge)
2. Log in to Twitter/X.com in your browser
3. Click Cookie-Editor icon → Export → Export as JSON
4. In Chi Tweet Scraper: Click 🍪 button → Paste → Save Cookies

Note: Cookies expire every 1-2 weeks. Refresh when prompted.""",
            ),
            (
                "6. API AUTHENTICATION (Paid)",
                """Uses third-party API services for reliable scraping.

Available: TwexAPI.io - $0.14 per 1,000 tweets

Setup:
1. Select API method from dropdown
2. Click ⚙ button → "Get API Key" link
3. Sign up at twexapi.io and get your key
4. Paste key → Test → Save""",
            ),
            (
                "7. SCRAPING MODES",
                """USERNAME MODE:
Enter Twitter handle (e.g., elonmusk) to scrape all their tweets in date range.

KEYWORDS MODE:
Enter comma-separated keywords (e.g., AI, technology)
• OR: Finds tweets with ANY keyword
• AND: Finds tweets with ALL keywords

BATCH MODE:
Create .txt file with usernames (one per line), check Batch mode, select file.

SCRAPE BY LINKS:
Create file with tweet URLs, go to Links tab, select file, start scrape.""",
            ),
            (
                "8. EXPORT FORMATS",
                """• Excel (.xlsx) - Best for viewing and filtering
• CSV (.csv) - Universal, fast for large datasets
• JSON (.json) - For developers
• SQLite (.db) - Database format for queries
• HTML (.html) - View in browser
• Markdown (.md) - For documentation""",
            ),
            (
                "9. FEATURES",
                """🌙 Dark Mode - Toggle in Help window
📅 Date Presets - Quick date range selection
🔍 Filters - Min likes/retweets, exclude RT/replies
📜 History - Track all past scrapes
📊 Analytics - Engagement stats after scraping
🔄 Auto-Retry - Automatic error recovery
⏸️ Breaks - Pause to avoid rate limits""",
            ),
            (
                "10. TROUBLESHOOTING",
                """Cookie Expired → Get fresh cookies from Cookie-Editor
Rate Limit → Wait 15-30 min, enable breaks
Network Error → Check internet, app auto-retries
No Tweets Found → Check username, expand date range
App Won't Start → Install requirements, check antivirus""",
            ),
            (
                "11. FAQ",
                """Q: Is this app safe?
A: Yes. Antivirus flags are false positives due to PyInstaller packaging.

Q: How much does it cost?
A: Cookies = FREE. API = ~$0.14 per 1,000 tweets.

Q: Can I scrape private accounts?
A: No, only public tweets.

Q: Is there a tweet limit?
A: No hard limit, but use breaks for large scrapes.""",
            ),
            (
                "SUPPORT",
                """Video Tutorials:
• Setup: https://youtu.be/RKX2sgQVgBg
• Full Tutorial: https://youtu.be/AbdpX6QZLm4

API Provider: https://twexapi.io

Made with ❤️ by OJ (Data Creator) | January 2025""",
            ),
        ]

        # Try to create PDF, fallback to text
        if filepath.endswith(".pdf"):
            try:
                self._create_pdf_documentation(filepath, doc_sections)
                messagebox.showinfo(
                    "Success", f"PDF Documentation saved to:\n{filepath}"
                )
                webbrowser.open(filepath)
                return
            except ImportError:
                # Fallback to text if reportlab not installed
                filepath = filepath.replace(".pdf", ".txt")
                messagebox.showinfo(
                    "Note",
                    "PDF library not installed. Saving as text file instead.\n\n"
                    "To enable PDF: pip install reportlab",
                )
            except Exception as e:
                filepath = filepath.replace(".pdf", ".txt")
                messagebox.showwarning(
                    "PDF Error", f"Could not create PDF: {e}\n\nSaving as text instead."
                )

        # Create text file
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write("CHI TWEET SCRAPER - COMPLETE USER DOCUMENTATION\n")
                f.write("Version 1.4.0\n")
                f.write("=" * 70 + "\n\n")

                for title, content in doc_sections[1:]:  # Skip the header
                    f.write(f"\n{title}\n")
                    f.write("-" * len(title) + "\n")
                    f.write(content + "\n\n")

            messagebox.showinfo("Success", f"Documentation saved to:\n{filepath}")
            webbrowser.open(filepath)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save documentation:\n{str(e)}")

    def _create_pdf_documentation(self, filepath, sections):
        """Create PDF documentation using reportlab."""
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_CENTER

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=HexColor("#2563eb"),
            spaceAfter=6,
            alignment=TA_CENTER,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=12,
            textColor=HexColor("#64748b"),
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=14,
            textColor=HexColor("#1e293b"),
            spaceBefore=20,
            spaceAfter=10,
            borderColor=HexColor("#2563eb"),
            borderWidth=0,
            borderPadding=0,
        )
        body_style = ParagraphStyle(
            "CustomBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=12,
        )

        story = []

        # Title page
        story.append(Spacer(1, 1.5 * inch))
        story.append(Paragraph("🐦 Chi Tweet Scraper", title_style))
        story.append(Paragraph(sections[0][1], subtitle_style))
        story.append(Spacer(1, 0.5 * inch))
        story.append(
            Paragraph("Professional Twitter/X Data Collection Tool", body_style)
        )
        story.append(PageBreak())

        # Content sections
        for title, content in sections[1:]:
            story.append(Paragraph(title, heading_style))
            # Convert line breaks to <br/>
            content_html = content.replace("\n", "<br/>")
            story.append(Paragraph(content_html, body_style))
            story.append(Spacer(1, 10))

        doc.build(story)


if __name__ == "__main__":
    cookies_dir = resource_path("cookies")
    exports_dir = resource_path(os.path.join("data", "exports"))
    os.makedirs(cookies_dir, exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)

    root = tk.Tk()
    app = TweetScraperApp(root)
    root.mainloop()
