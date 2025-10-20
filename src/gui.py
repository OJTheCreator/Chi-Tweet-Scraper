import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from tkinter.scrolledtext import ScrolledText
import threading
import asyncio
from datetime import datetime
import os
import sys
from PIL import Image, ImageTk
import webbrowser

# --- Project imports ---
from src.create_cookie import convert_editthiscookie_to_twikit_format
from src.scraper import scrape_tweets, scrape_tweet_links_file


# Utility for PyInstaller resource path
def resource_path(relative_path):
    try:
        # When bundled by PyInstaller
        base_path = sys._MEIPASS
    except AttributeError:
        # When running normally
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)


class TweetScraperApp:
    def __init__(self, root):
        self.root = root
        root.title("Chi Tweet Scraper")
        root.geometry("750x750")
        root.resizable(True, True)
        root.minsize(750, 750)

        # Configure root grid weights for responsive design
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.task = None
        self.current_task_type = None  # Track which tab is running: "main" or "links"
        self.file_path = None
        self.links_file_path = None
        self.save_dir = tk.StringVar(
            value=os.path.join(os.path.dirname(__file__), "..", "data", "exports")
        )

        # Create main container with padding
        self.main_frame = ttk.Frame(root, padding="15")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.columnconfigure(0, weight=1)

        # Create a Notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.notebook.columnconfigure(0, weight=1)
        self.notebook.rowconfigure(0, weight=1)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Create frames for tabs
        self.main_tab = ttk.Frame(self.notebook, padding="0")
        self.links_tab = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.main_tab, text="Main")
        self.notebook.add(self.links_tab, text="Scrape by Links")

        # Configure proper row weights
        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.rowconfigure(0, weight=0)
        self.main_tab.rowconfigure(1, weight=0)
        self.main_tab.rowconfigure(2, weight=0)
        self.main_tab.rowconfigure(3, weight=0)
        self.main_tab.rowconfigure(4, weight=0)
        self.main_tab.rowconfigure(5, weight=1)

        # Create widgets in the main tab
        self.create_widgets_main_tab()

        # Create widgets for the links tab
        self.create_links_tab()

    def on_tab_changed(self, event):
        """Handle tab switch - warn if scraping is in progress."""
        if self.task and not self.task.done():
            messagebox.showwarning(
                "Scraping in Progress",
                f"A {self.current_task_type} scrape is currently running.\n"
                "Please wait for it to complete or click Stop.",
            )
            # Switch back to the active tab
            active_tab = 0 if self.current_task_type == "main" else 1
            self.notebook.select(active_tab)

    def create_widgets_main_tab(self):
        current_row = 0
        current_row = self.create_header_section(current_row)
        current_row = self.create_config_section(current_row)
        current_row = self.create_search_section(current_row)
        current_row = self.create_cookie_section(current_row)
        current_row = self.create_controls_section(current_row)
        self.create_status_section(current_row)

    def create_header_section(self, row):
        header_frame = ttk.Frame(self.main_tab)
        header_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        header_frame.columnconfigure(1, weight=1)

        try:
            logo_file = resource_path(os.path.join("assets", "logo.png"))
            img = Image.open(logo_file).resize((60, 60), Image.Resampling.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            ttk.Label(header_frame, image=self.logo_img).grid(
                row=0, column=0, padx=(0, 15)
            )
        except Exception:
            pass

        title_frame = ttk.Frame(header_frame)
        title_frame.grid(row=0, column=1, sticky="w")

        ttk.Label(
            title_frame, text="Chi Tweet Scraper", font=("Segoe UI", 16, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_frame,
            text="Extract tweets with ease",
            font=("Segoe UI", 9),
            foreground="gray",
        ).grid(row=1, column=0, sticky="w")

        return row + 1

    def create_config_section(self, row):
        config_frame = ttk.LabelFrame(
            self.main_tab,
            text="Configuration",
            padding="10",
        )
        config_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Export Format:").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.format_var = tk.StringVar(value="Excel")
        format_combo = ttk.Combobox(
            config_frame,
            textvariable=self.format_var,
            values=["Excel", "CSV"],
            state="readonly",
            width=15,
        )
        format_combo.grid(row=0, column=1, sticky="w", pady=(0, 8))

        ttk.Label(config_frame, text="Save Folder:").grid(
            row=1, column=0, sticky="w", pady=(0, 8)
        )

        folder_frame = ttk.Frame(config_frame)
        folder_frame.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        folder_frame.columnconfigure(0, weight=1)

        ttk.Entry(folder_frame, textvariable=self.save_dir, state="readonly").grid(
            row=0, column=0, sticky="ew", padx=(0, 10)
        )
        ttk.Button(folder_frame, text="Browse", command=self.choose_folder).grid(
            row=0, column=1
        )

        self.batch_var = tk.BooleanVar(value=False)
        batch_check = ttk.Checkbutton(
            config_frame,
            text="Batch mode (load from file)",
            variable=self.batch_var,
            command=self.toggle_batch,
        )
        batch_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.file_btn = ttk.Button(
            config_frame, text="Select File", command=self.select_file, state="disabled"
        )
        self.file_btn.grid(row=3, column=1, sticky="w", pady=(5, 0))

        return row + 1

    def create_search_section(self, row):
        search_frame = ttk.LabelFrame(
            self.main_tab,
            text="Search Parameters",
            padding="10",
        )
        search_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Search by:").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self.mode_var = tk.StringVar(value="Username")
        self.mode_menu = ttk.Combobox(
            search_frame,
            textvariable=self.mode_var,
            values=["Username", "Keywords"],
            state="readonly",
            width=20,
        )
        self.mode_menu.grid(row=0, column=1, sticky="w", pady=(0, 8))
        self.mode_menu.bind("<<ComboboxSelected>>", self.update_mode)

        self.username_label = ttk.Label(search_frame, text="Username:")
        self.username_label.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.username_entry = ttk.Entry(search_frame, width=30)
        self.username_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))

        self.keyword_label = ttk.Label(search_frame, text="Keywords:")
        self.keyword_entry = ttk.Entry(search_frame, width=30)

        self.op_label = ttk.Label(search_frame, text="Operator:")
        self.op_var = tk.StringVar(value="OR")
        self.op_menu = ttk.Combobox(
            search_frame,
            textvariable=self.op_var,
            values=["OR", "AND"],
            state="readonly",
            width=10,
        )

        date_frame = ttk.Frame(search_frame)
        date_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        date_frame.columnconfigure(1, weight=1)
        date_frame.columnconfigure(3, weight=1)

        ttk.Label(date_frame, text="From:").grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        self.start_entry = ttk.Entry(date_frame, width=15)
        self.start_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))

        ttk.Label(date_frame, text="To:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.end_entry = ttk.Entry(date_frame, width=15)
        self.end_entry.grid(row=0, column=3, sticky="w")

        ttk.Label(
            date_frame,
            text="Format: YYYY-MM-DD",
            font=("Segoe UI", 8),
            foreground="gray",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

        return row + 1

    def create_cookie_section(self, row):
        self.cookie_expanded = tk.BooleanVar(value=False)

        cookie_frame = ttk.LabelFrame(
            self.main_tab,
            text="Twitter Cookies",
            padding="10",
        )
        cookie_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        cookie_frame.columnconfigure(0, weight=1)

        toggle_frame = ttk.Frame(cookie_frame)
        toggle_frame.grid(row=0, column=0, sticky="ew")

        self.cookie_toggle = ttk.Button(
            toggle_frame, text="▶ Show Cookie Input", command=self.toggle_cookie_section
        )
        self.cookie_toggle.grid(row=0, column=0, sticky="w")

        self.cookie_input_frame = ttk.Frame(cookie_frame)
        self.cookie_input_frame.columnconfigure(0, weight=1)

        ttk.Label(self.cookie_input_frame, text="Paste cookie JSON:").grid(
            row=0, column=0, sticky="w", pady=(10, 5)
        )

        self.cookie_text = tk.Text(
            self.cookie_input_frame, width=60, height=4, wrap=tk.WORD
        )
        self.cookie_text.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Button(
            self.cookie_input_frame, text="Save Cookies", command=self.save_cookies
        ).grid(row=2, column=0, sticky="e")

        return row + 1

    def create_controls_section(self, row):
        controls_frame = ttk.Frame(self.main_tab)
        controls_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        controls_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(
            controls_frame, length=300, mode="indeterminate"
        )
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.progress.grid_remove()

        status_button_frame = ttk.Frame(controls_frame)
        status_button_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        status_button_frame.columnconfigure(0, weight=1)

        self.count_lbl = ttk.Label(
            status_button_frame, text="Ready to scrape", foreground="gray"
        )
        self.count_lbl.grid(row=0, column=0, sticky="w")

        button_frame = ttk.Frame(status_button_frame)
        button_frame.grid(row=0, column=1, sticky="e")

        self.scrape_button = ttk.Button(
            button_frame, text="Start Scraping", command=self.start_scrape_thread
        )
        self.scrape_button.grid(row=0, column=0, padx=(0, 5))

        self.stop_btn = ttk.Button(
            button_frame, text="Stop", command=self.stop_scrape, state="disabled"
        )
        self.stop_btn.grid(row=0, column=1, padx=(0, 5))

        ttk.Button(button_frame, text="Help", command=self.show_guide).grid(
            row=0, column=2
        )

        return row + 1

    def create_status_section(self, row):
        log_frame = ttk.LabelFrame(self.main_tab, text="Activity Log", padding="10")
        log_frame.grid(row=row, column=0, sticky="nsew", pady=(0, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(
            log_frame,
            width=70,
            height=6,
            bg="#f8f9fa",
            font=("Consolas", 9),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(log_frame, text="Clear", command=self.clear_logs).grid(
            row=1, column=0, sticky="e", pady=(5, 0)
        )

    def create_links_tab(self):
        self.links_tab.columnconfigure(0, weight=1)
        self.links_tab.rowconfigure(4, weight=1)

        container = ttk.Frame(self.links_tab)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)

        ttk.Label(
            container,
            text="Scrape tweets from a file containing tweet links (.txt or .xlsx).",
            font=("Segoe UI", 10),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        # File selection row
        file_frame = ttk.Frame(container)
        file_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        file_frame.columnconfigure(0, weight=1)

        self.links_file_var = tk.StringVar(value="")
        ttk.Entry(file_frame, textvariable=self.links_file_var, state="readonly").grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(file_frame, text="Browse...", command=self.select_links_file).grid(
            row=0, column=1
        )

        # Buttons row
        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=2, column=0, sticky="e", pady=(0, 8))

        self.links_scrape_btn = ttk.Button(
            btn_frame, text="Start Link Scrape", command=self.start_links_thread
        )
        self.links_scrape_btn.grid(row=0, column=0, padx=(0, 8))

        ttk.Button(btn_frame, text="Help", command=self.show_guide).grid(
            row=0, column=1, padx=(0, 8)
        )

        # Notes
        ttk.Label(
            container,
            text="Notes: Text files should have one tweet URL per line. Excel files should have URLs in the first column.",
            font=("Segoe UI", 8),
            foreground="gray",
            wraplength=700,
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))

        # Status section for links tab
        links_log_frame = ttk.LabelFrame(container, text="Activity Log", padding="10")
        links_log_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        links_log_frame.columnconfigure(0, weight=1)
        links_log_frame.rowconfigure(0, weight=1)

        self.links_log_text = ScrolledText(
            links_log_frame,
            width=70,
            height=6,
            bg="#f8f9fa",
            font=("Consolas", 9),
        )
        self.links_log_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(links_log_frame, text="Clear", command=self.clear_links_logs).grid(
            row=1, column=0, sticky="e", pady=(5, 0)
        )

    def toggle_cookie_section(self):
        if self.cookie_expanded.get():
            self.cookie_input_frame.grid_remove()
            self.cookie_toggle.config(text="▶ Show Cookie Input")
            self.cookie_expanded.set(False)
        else:
            self.cookie_input_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
            self.cookie_toggle.config(text="▼ Hide Cookie Input")
            self.cookie_expanded.set(True)

    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_dir.set(folder)

    def toggle_batch(self):
        on = self.batch_var.get()
        self.file_btn.config(state="normal" if on else "disabled")
        self.mode_menu.config(state="disabled" if on else "readonly")
        self.username_entry.config(state="disabled" if on else "normal")
        self.keyword_entry.config(state="disabled" if on else "normal")
        self.op_menu.config(state="disabled" if on else "readonly")

    def select_file(self):
        path = filedialog.askopenfilename(
            title="Select username file",
            filetypes=[("Text/CSV", "*.txt;*.csv"), ("All", "*.*")],
        )
        if path:
            self.file_path = path
            filename = os.path.basename(path)
            self.log(f"Loaded file: {filename}")

    def select_links_file(self):
        path = filedialog.askopenfilename(
            title="Select tweet links file",
            filetypes=[
                ("Text files", "*.txt"),
                ("Excel files", "*.xlsx;*.xls"),
                ("All", "*.*"),
            ],
        )
        if path:
            # Validate file extension
            ext = os.path.splitext(path)[1].lower()
            if ext not in [".txt", ".xlsx", ".xls"]:
                messagebox.showerror(
                    "Invalid File",
                    "Please select a .txt or .xlsx/.xls file.",
                )
                return

            self.links_file_path = path
            self.links_file_var.set(path)
            filename = os.path.basename(path)
            self.links_log(f"✅ Loaded links file: {filename}")

    def update_mode(self, *_):
        if self.mode_var.get() == "Username":
            self.username_label.grid(row=1, column=0, sticky="w", pady=(0, 8))
            self.username_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))
            self.keyword_label.grid_remove()
            self.keyword_entry.grid_remove()
            self.op_label.grid_remove()
            self.op_menu.grid_remove()
        else:
            self.username_label.grid_remove()
            self.username_entry.grid_remove()
            self.keyword_label.grid(row=1, column=0, sticky="w", pady=(0, 8))
            self.keyword_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))
            self.op_label.grid(row=2, column=0, sticky="w", pady=(0, 8))
            self.op_menu.grid(row=2, column=1, sticky="w", pady=(0, 8))

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def links_log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.links_log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.links_log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def clear_links_logs(self):
        self.links_log_text.delete("1.0", tk.END)

    def save_cookies(self):
        raw = self.cookie_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("No Cookies", "Please paste cookie JSON first.")
            return
        if convert_editthiscookie_to_twikit_format(raw):
            self.log("✓ Cookies saved successfully")
            messagebox.showinfo("Success", "Cookies saved successfully!")
        else:
            self.log("✗ Failed to save cookies (invalid JSON)")
            self.cookie_text.delete("1.0", tk.END)
            messagebox.showerror(
                "Error", "Invalid cookie format. Please check your JSON."
            )

    def start_scrape_thread(self):
        fmt = self.format_var.get().lower()
        start, end = self.start_entry.get().strip(), self.end_entry.get().strip()
        save_dir = self.save_dir.get()

        # Check if another task is running
        if self.task and not self.task.done():
            messagebox.showwarning(
                "Task Running",
                "A scraping task is already in progress. Please wait or click Stop.",
            )
            return

        if not start or not end:
            messagebox.showerror(
                "Missing Dates", "Please enter both start and end dates."
            )
            return

        try:
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "Invalid Date", "Please use YYYY-MM-DD format for dates."
            )
            return

        if not os.path.isdir(save_dir):
            messagebox.showerror(
                "Invalid Path", f"Save directory not found:\n{save_dir}"
            )
            return

        if self.batch_var.get():
            if not self.file_path:
                messagebox.showwarning("No File", "Please select a username file.")
                return
            with open(self.file_path, encoding="utf-8") as f:
                txt = f.read().replace("\n", ",")
            users = [u.strip() for u in txt.split(",") if u.strip()]
            if not users:
                messagebox.showwarning("Empty File", "No usernames found in file.")
                return
            target = ("batch", users)
        else:
            mode = self.mode_var.get()
            user = self.username_entry.get().strip() if mode == "Username" else None
            kws = (
                [k.strip() for k in self.keyword_entry.get().split(",") if k.strip()]
                if mode == "Keywords"
                else None
            )

            if (mode == "Username" and not user) or (mode == "Keywords" and not kws):
                messagebox.showwarning(
                    "Missing Input",
                    "Please enter a username or keywords to search for.",
                )
                return
            target = ("single", user, kws)

        # UI state changes
        self.current_task_type = "main"
        self.scrape_button.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.progress.start(30)
        self.count_lbl.config(text="Initializing scraper...", foreground="blue")
        self.clear_logs()
        self.log("🚀 Starting scrape operation...")

        threading.Thread(
            target=self._run_scrape,
            args=(target, start, end, fmt, save_dir),
            daemon=True,
        ).start()

    def _run_scrape(self, target, start, end, fmt, save_dir):
        def progress_cb(msg):
            if isinstance(msg, str):
                self.log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if target[0] == "batch":

                async def batch_task():
                    total_tweets = 0
                    for i, u in enumerate(target[1], 1):
                        if self.task and self.task.done():
                            break
                        progress_cb(f"📥 Processing user {i}/{len(target[1])}: {u}")
                        out, cnt = await scrape_tweets(
                            username=u,
                            start_date=start,
                            end_date=end,
                            keywords=None,
                            use_and=False,
                            export_format=fmt,
                            progress_callback=progress_cb,
                            should_stop_callback=lambda: (
                                self.task.done() if self.task else False
                            ),
                            save_dir=save_dir,
                        )
                        total_tweets += cnt
                        progress_cb(f"✅ {cnt} tweets saved for {u}")
                    return [], total_tweets

                self.task = loop.create_task(batch_task())
                output, total = loop.run_until_complete(self.task)
                self.log(f"🎉 Batch complete! Total tweets: {total}")
                messagebox.showinfo(
                    "Batch Complete", f"Successfully scraped {total} tweets!"
                )

            else:
                _, user, kws = target
                self.task = loop.create_task(
                    scrape_tweets(
                        username=user,
                        start_date=start,
                        end_date=end,
                        keywords=kws,
                        use_and=(self.op_var.get() == "AND"),
                        export_format=fmt,
                        progress_callback=progress_cb,
                        should_stop_callback=lambda: (
                            self.task.done() if self.task else False
                        ),
                        save_dir=save_dir,
                    )
                )
                output, total = loop.run_until_complete(self.task)
                self.log(
                    f"🎉 Scraping complete! {total} tweets saved to: {os.path.basename(output)}"
                )
                messagebox.showinfo("Success", f"✅ {total} tweets saved to:\n{output}")

        except asyncio.CancelledError:
            self.log("⚠️ Scraping cancelled by user")
            self.count_lbl.config(text="Cancelled", foreground="orange")
        except Exception as e:
            self.log(f"❌ Error: {e}")
            self.count_lbl.config(text="Error occurred", foreground="red")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        finally:
            self.progress.stop()
            self.progress.grid_remove()
            self.scrape_button.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.count_lbl.config(text="Ready to scrape", foreground="gray")
            self.task = None
            self.current_task_type = None

    def start_links_thread(self):
        """Start link-based scraping in a thread."""
        fmt = self.format_var.get().lower()
        save_dir = self.save_dir.get()
        links_path = self.links_file_path

        # Check if another task is running
        if self.task and not self.task.done():
            messagebox.showwarning(
                "Task Running",
                "A scraping task is already in progress. Please wait or click Stop.",
            )
            return

        if not links_path or not os.path.exists(links_path):
            messagebox.showwarning(
                "No File", "Please select a tweet links file (.txt or .xlsx)."
            )
            return

        # Validate file extension again before starting
        ext = os.path.splitext(links_path)[1].lower()
        if ext not in [".txt", ".xlsx", ".xls"]:
            messagebox.showerror(
                "Invalid File",
                "Invalid file format. Please select a .txt or .xlsx/.xls file.",
            )
            return

        if not os.path.isdir(save_dir):
            messagebox.showerror(
                "Invalid Path", f"Save directory not found:\n{save_dir}"
            )
            return

        # UI state changes
        self.current_task_type = "links"
        self.links_scrape_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.progress.start(30)
        self.count_lbl.config(text="Initializing link scraper...", foreground="blue")
        self.clear_links_logs()
        self.links_log("🚀 Starting link-based scrape operation...")

        threading.Thread(
            target=self._run_links,
            args=(links_path, fmt, save_dir),
            daemon=True,
        ).start()

    def _run_links(self, links_path, fmt, save_dir):
        def progress_cb(msg):
            if isinstance(msg, str):
                self.links_log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:

            async def links_task():
                out, cnt, failed = await scrape_tweet_links_file(
                    file_path=links_path,
                    export_format=fmt,
                    save_dir=save_dir,
                    progress_callback=progress_cb,
                    should_stop_callback=lambda: (
                        self.task.done() if self.task else False
                    ),
                )
                return out, cnt, failed

            self.task = loop.create_task(links_task())
            output, total, failed = loop.run_until_complete(self.task)

            self.links_log(
                f"🎉 Link scraping complete! {total} tweets saved to: {os.path.basename(output)}"
            )
            if failed:
                self.links_log(f"⚠️ {failed} links failed during scraping.")
            messagebox.showinfo("Success", f"✅ {total} tweets saved to:\n{output}")

        except asyncio.CancelledError:
            self.links_log("⚠️ Link scraping cancelled by user")
            self.count_lbl.config(text="Cancelled", foreground="orange")
        except Exception as e:
            self.links_log(f"❌ Error: {e}")
            self.count_lbl.config(text="Error occurred", foreground="red")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        finally:
            self.progress.stop()
            self.progress.grid_remove()
            self.links_scrape_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.count_lbl.config(text="Ready to scrape", foreground="gray")
            self.task = None
            self.current_task_type = None

    def stop_scrape(self):
        if self.task and not self.task.done():
            self.task.cancel()
            if self.current_task_type == "main":
                self.log("🛑 Stop requested...")
            else:
                self.links_log("🛑 Stop requested...")

    def show_guide(self):
        guide_text = """Welcome to Chi Tweet Scraper! Here's a step-by-step guide to help you get started:

    1. Setting Up Cookies (Required):
    • Install the "cookie-editor" browser extension (Chrome/Firefox/Edge).
    • Log in to Twitter in your browser.
    • Export your cookies as JSON and paste them into Chi Tweet Scraper.

    2. Configuring the Settings:
    • Choose export format (Excel/CSV).
    • Select save folder.
    • Use batch mode to load multiple usernames from file.

    3. Setting Search Parameters:
    • Search by username or keywords.
    • Enter a date range (YYYY-MM-DD).

    4. Starting the Scraping Process:
    • Click "Start Scraping" to begin.
    • Monitor progress in the Activity Log.
    • Use "Stop" if needed.

    Tips:
    • Use batch mode for multiple users.
    • Narrow date ranges for better results.
    • Check Activity Log for progress.

    Installation Guide (YouTube):
    https://youtu.be/RKX2sgQVgBg

    How to Use Chi Tweet Scraper (YouTube):
    https://youtu.be/AbdpX6QZLm4
    """

        # Create a custom dialog for better formatting
        guide_window = tk.Toplevel(self.root)
        guide_window.title("User Guide")
        guide_window.geometry("500x450")
        guide_window.resizable(False, False)
        guide_window.transient(self.root)
        guide_window.grab_set()

        # Center the window
        guide_window.update_idletasks()
        x = (guide_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (guide_window.winfo_screenheight() // 2) - (450 // 2)
        guide_window.geometry(f"500x450+{x}+{y}")

        # Add text widget
        text_frame = ttk.Frame(guide_window, padding="20")
        text_frame.pack(fill="both", expand=True)

        text_widget = ScrolledText(text_frame, wrap=tk.WORD, font=("Segoe UI", 10))
        text_widget.pack(fill="both", expand=True)

        # Insert main guide text
        text_widget.insert("1.0", guide_text)

        # Make YouTube links clickable
        def add_hyperlink(url, start, end):
            text_widget.tag_add(url, start, end)
            text_widget.tag_config(url, foreground="blue", underline=1)
            text_widget.tag_bind(url, "<Button-1>", lambda e: webbrowser.open(url))

        # Highlight & bind each link
        start_idx = text_widget.search("https://youtu.be/RKX2sgQVgBg", "1.0", tk.END)
        if start_idx:
            end_idx = f"{start_idx}+{len('https://youtu.be/RKX2sgQVgBg')}c"
            add_hyperlink("https://youtu.be/RKX2sgQVgBg", start_idx, end_idx)

        start_idx = text_widget.search("https://youtu.be/AbdpX6QZLm4", "1.0", tk.END)
        if start_idx:
            end_idx = f"{start_idx}+{len('https://youtu.be/AbdpX6QZLm4')}c"
            add_hyperlink("https://youtu.be/AbdpX6QZLm4", start_idx, end_idx)

        text_widget.config(state="disabled")

        # Close button
        ttk.Button(guide_window, text="Close", command=guide_window.destroy).pack(
            pady=(0, 20)
        )


if __name__ == "__main__":
    # Ensure required directories exist (PyInstaller-safe)
    cookies_dir = resource_path("cookies")
    exports_dir = resource_path(os.path.join("data", "exports"))
    os.makedirs(cookies_dir, exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)

    root = tk.Tk()

    # Set a nice theme if available
    try:
        style = ttk.Style()
        available_themes = style.theme_names()
        if "vista" in available_themes:
            style.theme_use("vista")
        elif "clam" in available_themes:
            style.theme_use("clam")
    except:
        pass

    app = TweetScraperApp(root)
    root.mainloop()
