import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from tkinter.scrolledtext import ScrolledText
import threading
import asyncio
from datetime import datetime
import os
import sys
from PIL import Image, ImageTk

# --- Project imports ---
from src.create_cookie import convert_editthiscookie_to_twikit_format
from src.scraper import scrape_tweets


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
        root.geometry("750x750")  # Fixed: Increased height to accommodate all content
        root.resizable(True, True)  # Fixed: Allow both horizontal and vertical resizing
        root.minsize(
            750, 750
        )  # Fixed: Increased minimum window size to fit all content

        # Configure root grid weights for responsive design
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.task = None
        self.file_path = None
        self.save_dir = tk.StringVar(
            value=os.path.join(os.path.dirname(__file__), "..", "data", "exports")
        )

        # Create main container with padding
        self.main_frame = ttk.Frame(root, padding="15")  # Fixed: Reduced padding
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.columnconfigure(0, weight=1)

        # Fixed: Configure proper row weights for all sections
        self.main_frame.rowconfigure(0, weight=0)  # Header - fixed height
        self.main_frame.rowconfigure(1, weight=0)  # Config - fixed height
        self.main_frame.rowconfigure(2, weight=0)  # Search - fixed height
        self.main_frame.rowconfigure(3, weight=0)  # Cookie - fixed height
        self.main_frame.rowconfigure(4, weight=0)  # Controls - fixed height
        self.main_frame.rowconfigure(5, weight=1)  # Status/Log - expandable

        self.create_widgets()

    def create_widgets(self):
        current_row = 0

        # Header section with logo and title
        current_row = self.create_header_section(current_row)

        # Configuration section
        current_row = self.create_config_section(current_row)

        # Search parameters section
        current_row = self.create_search_section(current_row)

        # Cookie section (collapsible)
        current_row = self.create_cookie_section(current_row)

        # Control buttons
        current_row = self.create_controls_section(current_row)

        # Status and logs section
        self.create_status_section(current_row)

    def create_header_section(self, row):
        # Header frame
        header_frame = ttk.Frame(self.main_frame)
        header_frame.grid(
            row=row, column=0, sticky="ew", pady=(0, 10)
        )  # Fixed: Reduced padding
        header_frame.columnconfigure(1, weight=1)

        # Logo
        try:
            logo_file = resource_path(os.path.join("assets", "logo.png"))
            img = Image.open(logo_file).resize((60, 60), Image.Resampling.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            ttk.Label(header_frame, image=self.logo_img).grid(
                row=0, column=0, padx=(0, 15)
            )
        except Exception:
            pass

        # Title and subtitle
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
        # Configuration frame
        config_frame = ttk.LabelFrame(
            self.main_frame,
            text="Configuration",
            padding="10",  # Fixed: Reduced padding
        )
        config_frame.grid(
            row=row, column=0, sticky="ew", pady=(0, 10)
        )  # Fixed: Reduced padding
        config_frame.columnconfigure(1, weight=1)

        # Export format
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

        # Save folder
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

        # Batch mode
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
        # Search parameters frame
        search_frame = ttk.LabelFrame(
            self.main_frame,
            text="Search Parameters",
            padding="10",  # Fixed: Reduced padding
        )
        search_frame.grid(
            row=row, column=0, sticky="ew", pady=(0, 10)
        )  # Fixed: Reduced padding
        search_frame.columnconfigure(1, weight=1)

        # Search mode
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

        # Username field
        self.username_label = ttk.Label(search_frame, text="Username:")
        self.username_label.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.username_entry = ttk.Entry(search_frame, width=30)
        self.username_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))

        # Keywords field (initially hidden)
        self.keyword_label = ttk.Label(search_frame, text="Keywords:")
        self.keyword_entry = ttk.Entry(search_frame, width=30)

        # Operator (initially hidden)
        self.op_label = ttk.Label(search_frame, text="Operator:")
        self.op_var = tk.StringVar(value="OR")
        self.op_menu = ttk.Combobox(
            search_frame,
            textvariable=self.op_var,
            values=["OR", "AND"],
            state="readonly",
            width=10,
        )

        # Date range in a sub-frame
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

        # Date format hint
        ttk.Label(
            date_frame,
            text="Format: YYYY-MM-DD",
            font=("Segoe UI", 8),
            foreground="gray",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))

        return row + 1

    def create_cookie_section(self, row):
        # Cookie section (expandable)
        self.cookie_expanded = tk.BooleanVar(value=False)

        cookie_frame = ttk.LabelFrame(
            self.main_frame,
            text="Twitter Cookies",
            padding="10",  # Fixed: Reduced padding
        )
        cookie_frame.grid(
            row=row, column=0, sticky="ew", pady=(0, 10)
        )  # Fixed: Reduced padding
        cookie_frame.columnconfigure(0, weight=1)

        # Toggle button
        toggle_frame = ttk.Frame(cookie_frame)
        toggle_frame.grid(row=0, column=0, sticky="ew")

        self.cookie_toggle = ttk.Button(
            toggle_frame, text="▶ Show Cookie Input", command=self.toggle_cookie_section
        )
        self.cookie_toggle.grid(row=0, column=0, sticky="w")

        # Cookie input (initially hidden)
        self.cookie_input_frame = ttk.Frame(cookie_frame)
        # Fixed: Configure column weight for proper expansion
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
        # Control buttons frame
        controls_frame = ttk.Frame(self.main_frame)
        controls_frame.grid(
            row=row, column=0, sticky="ew", pady=(0, 10)
        )  # Fixed: Reduced padding
        # Fixed: Configure column weights for proper layout
        controls_frame.columnconfigure(0, weight=1)

        # Progress bar
        self.progress = ttk.Progressbar(
            controls_frame, length=300, mode="indeterminate"
        )
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.progress.grid_remove()

        # Status label and buttons frame
        status_button_frame = ttk.Frame(controls_frame)
        status_button_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        status_button_frame.columnconfigure(0, weight=1)

        # Status label
        self.count_lbl = ttk.Label(
            status_button_frame, text="Ready to scrape", foreground="gray"
        )
        self.count_lbl.grid(row=0, column=0, sticky="w")

        # Control buttons
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
        # Status and logs section
        log_frame = ttk.LabelFrame(self.main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=row, column=0, sticky="nsew", pady=(0, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Fixed: This was already correct, but ensure it's properly weighted
        # This section should expand to fill remaining space
        # (Already handled in __init__ with rowconfigure)

        self.log_text = ScrolledText(
            log_frame,
            width=70,
            height=6,
            bg="#f8f9fa",
            font=("Consolas", 9),  # Fixed: Reduced height from 8 to 6
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # Clear logs button
        ttk.Button(log_frame, text="Clear", command=self.clear_logs).grid(
            row=1, column=0, sticky="e", pady=(5, 0)
        )

    def toggle_cookie_section(self):
        if self.cookie_expanded.get():
            # Collapse
            self.cookie_input_frame.grid_remove()
            self.cookie_toggle.config(text="▶ Show Cookie Input")
            self.cookie_expanded.set(False)
        else:
            # Expand
            self.cookie_input_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
            self.cookie_toggle.config(text="▼ Hide Cookie Input")
            self.cookie_expanded.set(True)

    # --- Helper methods (keeping your original logic) ---
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

    def update_mode(self, *_):
        if self.mode_var.get() == "Username":
            # Show username fields
            self.username_label.grid(row=1, column=0, sticky="w", pady=(0, 8))
            self.username_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))
            # Hide keyword fields
            self.keyword_label.grid_remove()
            self.keyword_entry.grid_remove()
            self.op_label.grid_remove()
            self.op_menu.grid_remove()
        else:
            # Hide username fields
            self.username_label.grid_remove()
            self.username_entry.grid_remove()
            # Show keyword fields
            self.keyword_label.grid(row=1, column=0, sticky="w", pady=(0, 8))
            self.keyword_entry.grid(row=1, column=1, sticky="w", pady=(0, 8))
            self.op_label.grid(row=2, column=0, sticky="w", pady=(0, 8))
            self.op_menu.grid(row=2, column=1, sticky="w", pady=(0, 8))

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_logs(self):
        self.log_text.delete("1.0", tk.END)

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
            messagebox.showerror(
                "Error", "Invalid cookie format. Please check your JSON."
            )

    # --- Scraping methods (keeping your original logic) ---
    def start_scrape_thread(self):
        fmt = self.format_var.get().lower()
        start, end = self.start_entry.get().strip(), self.end_entry.get().strip()
        save_dir = self.save_dir.get()

        # Validation
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
        def progress_cb(x):
            if isinstance(x, int):
                self.count_lbl.config(text=f"Tweets scraped: {x}", foreground="green")
            else:
                self.log(str(x))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if target[0] == "batch":

                async def batch_task():
                    total_tweets = 0
                    for i, u in enumerate(target[1], 1):
                        progress_cb(f"📥 Processing user {i}/{len(target[1])}: {u}")
                        out, cnt = await scrape_tweets(
                            username=u,
                            start_date=start,
                            end_date=end,
                            keywords=None,
                            use_and=False,
                            export_format=fmt,
                            progress_callback=progress_cb,
                            should_stop_callback=lambda: self.task.done(),
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
                        should_stop_callback=lambda: self.task.done(),
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
            # Reset UI state
            self.progress.stop()
            self.progress.grid_remove()
            self.scrape_button.config(state="normal")
            self.stop_btn.config(state="disabled")
            if not hasattr(self, "_cancelled"):
                self.count_lbl.config(text="Ready to scrape", foreground="gray")

    def stop_scrape(self):
        if self.task and not self.task.done():
            self.task.cancel()
            self.log("🛑 Stop requested...")
            self._cancelled = True

    def show_guide(self):
        guide_text = """Welcome to Chi Tweet Scraper! Here's a step-by-step guide to help you get started:

    1. 🍪 Setting Up Cookies (Required):
       • First, install the "cookie-editor" browser extension (available for Chrome, Firefox, and Edge).
       • Log in to your Twitter account in your browser.
       • Use the cookie-editor extension to export your Twitter cookies as a JSON file.
       • In the Chi Tweet Scraper app, click the "Show Cookie Input" button.
       • Paste the copied JSON into the provided text box and click "Save Cookies."

    2. ⚙️ Configuring the Settings:
       • Choose the format for your exported data (Excel or CSV).
       • Select the folder where you want the scraped data to be saved.
       • If you want to scrape tweets for multiple users, enable "Batch mode" and upload a file containing the usernames.

    3. 🔍 Setting Search Parameters:
       • Decide whether you want to search by "Username" or "Keywords."
       • If searching by username, enter the Twitter username.
       • If searching by keywords, enter the keywords separated by commas (e.g., "python, AI, data").
       • Specify the date range for the tweets you want to scrape. Use the format YYYY-MM-DD (e.g., 2023-01-01 to 2023-12-31).

    4. ▶️ Starting the Scraping Process:
       • Click the "Start Scraping" button to begin.
       • You can monitor the progress in the "Activity Log" section.
       • If you need to stop the process, click the "Stop" button.

    Tips for Best Results:
    • Use "Batch mode" if you want to scrape tweets for multiple usernames at once.
    • Narrow down your search by specifying a date range to focus on specific time periods.
    • Check the "Activity Log" for detailed updates and progress information.

    Happy scraping!"""

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

        # Add text widget with scrollbar
        text_frame = ttk.Frame(guide_window, padding="20")
        text_frame.pack(fill="both", expand=True)

        text_widget = ScrolledText(text_frame, wrap=tk.WORD, font=("Segoe UI", 10))
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", guide_text)
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
