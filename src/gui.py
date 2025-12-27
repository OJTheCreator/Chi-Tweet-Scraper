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
from src.state_manager import StateManager

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
        self.state_manager = StateManager()
        self.paused_for_cookies = False
        self.paused_for_network = False

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
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(0, weight=1)

        # Create a Notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.columnconfigure(0, weight=1)
        self.notebook.rowconfigure(0, weight=1)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Create frames for tabs
        self.main_tab = ttk.Frame(self.notebook, padding="8")
        self.links_tab = ttk.Frame(self.notebook, padding="8")

        self.notebook.add(self.main_tab, text="Main")
        self.notebook.add(self.links_tab, text="Scrape by Links")

        # Configure proper row weights for main tab
        self.main_tab.columnconfigure(0, weight=1)
        self.main_tab.rowconfigure(6, weight=1)  # Log section gets all extra space

        # Create widgets in the main tab
        self.create_widgets_main_tab()

        # Create widgets for the links tab
        self.create_links_tab()

        # Check for existing state and show resume dialog
        self.root.after(500, self.check_for_saved_state)

    def check_for_saved_state(self):
        """Check if there's a saved state and offer to resume."""
        if self.state_manager.has_saved_state():
            summary = self.state_manager.get_state_summary()

            response = messagebox.askyesnocancel(
                "Resume Previous Session?",
                f"Found an incomplete scraping session:\n\n{summary}\n\n"
                "Would you like to resume where you left off?\n\n"
                "• Yes: Resume from saved point\n"
                "• No: Start fresh (clears saved state)\n"
                "• Cancel: Keep state for later",
                icon="question",
            )

            if response is True:  # Yes - Resume
                self.resume_from_state()
            elif response is False:  # No - Clear state
                self.state_manager.clear_state()
                self.log("🗑️ Previous session cleared. Starting fresh.")

    def resume_from_state(self):
        """Resume scraping from saved state."""
        state = self.state_manager.load_state()
        if not state:
            messagebox.showerror("Error", "Could not load saved state.")
            return

        mode = state.get("mode")

        if mode == "batch":
            self.resume_batch_scrape(state)
        elif mode == "single":
            self.resume_single_scrape(state)
        elif mode == "links":
            self.resume_links_scrape(state)

    def resume_batch_scrape(self, state):
        """Resume batch scraping from saved state."""
        # Switch to main tab
        self.notebook.select(0)

        # Restore settings
        settings = state.get("settings", {})
        self.format_var.set(settings.get("export_format", "Excel"))
        self.save_dir.set(settings.get("save_dir", self.save_dir.get()))
        self.start_entry.delete(0, tk.END)
        self.start_entry.insert(0, settings.get("start_date", ""))
        self.end_entry.delete(0, tk.END)
        self.end_entry.insert(0, settings.get("end_date", ""))

        # Enable batch mode
        self.batch_var.set(True)
        self.toggle_batch()
        self.file_path = state.get("file_path")

        # Get remaining usernames
        all_usernames = state.get("usernames", [])
        current_index = state.get("current_index", 0)
        remaining_usernames = all_usernames[current_index:]

        self.log(
            f"🔄 Resuming batch scrape from user {current_index + 1}/{len(all_usernames)}"
        )

        # Start scraping with resume state
        self.start_batch_scrape_with_resume(remaining_usernames, settings, state)

    def resume_single_scrape(self, state):
        """Resume single user scraping from saved state."""
        # Switch to main tab
        self.notebook.select(0)

        # Restore settings
        settings = state.get("settings", {})
        self.format_var.set(settings.get("export_format", "Excel"))
        self.save_dir.set(settings.get("save_dir", self.save_dir.get()))
        self.start_entry.delete(0, tk.END)
        self.start_entry.insert(0, settings.get("start_date", ""))
        self.end_entry.delete(0, tk.END)
        self.end_entry.insert(0, settings.get("end_date", ""))

        username = state.get("current_username")
        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(0, username)

        self.log(f"🔄 Resuming scrape for @{username}")

        # Start scraping with resume state
        self.start_single_scrape_with_resume(settings, state)

    def resume_links_scrape(self, state):
        """Resume link scraping from saved state."""
        # Switch to links tab
        self.notebook.select(1)
        
    def start_batch_scrape_with_resume(self, remaining_usernames, settings, state):
        """Resume batch scraping with remaining users."""
        self.log("🔄 Starting batch scrape with resume state...")
        # Restore UI and start scraping
        # For now, this will just call the normal start process
        messagebox.showinfo(
            "Resume",
            f"Resuming batch scrape with {len(remaining_usernames)} remaining users."
        )
        # TODO: Implement full resume logic with state tracking

    def start_single_scrape_with_resume(self, settings, state):
        """Resume single user scraping."""
        self.log("🔄 Starting single user scrape with resume state...")
        messagebox.showinfo("Resume", "Resuming single user scrape.")
        # TODO: Implement full resume logic with state tracking

    def start_links_scrape_with_resume(self, settings, state):
        """Resume link scraping."""
        self.links_log("🔄 Starting link scrape with resume state...")
        messagebox.showinfo("Resume", "Resuming link scrape.")
        # TODO: Implement full resume logic with state tracking   

        # Restore settings
        settings = state.get("settings", {})
        self.links_file_path = state.get("links_file_path")
        self.links_file_var.set(self.links_file_path)

        self.links_log(f"🔄 Resuming link scrape from saved position")

        # Start scraping with resume state
        self.start_links_scrape_with_resume(settings, state)

    def show_cookie_expired_dialog(self):
        """Show dialog when cookies expire during scraping."""
        self.paused_for_cookies = True
        self.root.after(0, self._show_cookie_dialog_ui)

    def _show_cookie_dialog_ui(self):
        """UI thread version of cookie expired dialog."""
        cookie_window = tk.Toplevel(self.root)
        cookie_window.title("🔑 Cookies Expired")
        cookie_window.geometry("500x400")
        cookie_window.resizable(False, False)
        cookie_window.transient(self.root)
        cookie_window.grab_set()

        # Center window
        cookie_window.update_idletasks()
        x = (cookie_window.winfo_screenwidth() // 2) - 250
        y = (cookie_window.winfo_screenheight() // 2) - 200
        cookie_window.geometry(f"500x400+{x}+{y}")

        main_frame = ttk.Frame(cookie_window, padding="20")
        main_frame.pack(fill="both", expand=True)

        # Warning icon and message
        ttk.Label(
            main_frame,
            text="⚠️ Authentication Expired",
            font=("Segoe UI", 14, "bold"),
            foreground="orange",
        ).pack(pady=(0, 10))

        ttk.Label(
            main_frame,
            text="Your Twitter cookies have expired.\nPlease update them to continue scraping.",
            font=("Segoe UI", 10),
            justify="center",
        ).pack(pady=(0, 15))

        # Cookie input
        ttk.Label(main_frame, text="Paste new cookie JSON:", font=("Segoe UI", 9)).pack(
            anchor="w", pady=(0, 5)
        )

        cookie_text = tk.Text(
            main_frame, width=55, height=8, wrap=tk.WORD, font=("Consolas", 8)
        )
        cookie_text.pack(fill="both", expand=True, pady=(0, 10))

        # Status label
        status_label = ttk.Label(main_frame, text="", foreground="gray")
        status_label.pack(pady=(0, 10))

        def save_and_resume():
            raw = cookie_text.get("1.0", tk.END).strip()
            if not raw:
                status_label.config(
                    text="❌ Please paste cookie JSON", foreground="red"
                )
                return

            from src.create_cookie import convert_editthiscookie_to_twikit_format

            if convert_editthiscookie_to_twikit_format(raw):
                status_label.config(
                    text="✅ Cookies saved! Resuming...", foreground="green"
                )
                self.paused_for_cookies = False
                cookie_window.after(1000, cookie_window.destroy)
            else:
                status_label.config(text="❌ Invalid cookie format", foreground="red")

        def cancel_scrape():
            self.paused_for_cookies = False
            if self.task and not self.task.done():
                self.task.cancel()
            cookie_window.destroy()

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(btn_frame, text="Save & Resume", command=save_and_resume).pack(
            side="right", padx=(5, 0)
        )

        ttk.Button(btn_frame, text="Cancel Scrape", command=cancel_scrape).pack(
            side="right"
        )

    def show_network_error_dialog(self, error_msg):
        """Show dialog when network fails during scraping."""
        self.paused_for_network = True

        response = messagebox.askretrycancel(
            "🔌 Network Error",
            f"Network connection failed:\n\n{error_msg}\n\n"
            "Your progress has been saved.\n\n"
            "Click 'Retry' when connection is restored,\n"
            "or 'Cancel' to stop scraping.",
            icon="warning",
        )

        if response:  # Retry
            self.paused_for_network = False
            # Continue scraping - the retry logic will handle it
        else:  # Cancel
            self.paused_for_network = False
            if self.task and not self.task.done():
                self.task.cancel()

    def save_scrape_state(self, mode, **kwargs):
        """Save current scraping state."""
        state_data = {"mode": mode, **kwargs}
        self.state_manager.save_state(state_data)

    # Modify your existing _run_scrape method to save state periodically:

    def _run_scrape(self, target, start, end, fmt, save_dir, break_settings):
        """Enhanced version with state saving and resume support."""

        def progress_cb(msg):
            if isinstance(msg, str):
                self.log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        def cookie_expired_cb(error_msg):
            """Called when cookies expire."""
            self.log(f"🔑 {error_msg}")
            self.show_cookie_expired_dialog()

            # Wait until cookies are updated
            while self.paused_for_cookies:
                asyncio.sleep(0.5)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if target[0] == "batch":

                async def batch_task():
                    total_tweets = 0
                    usernames = target[1]

                    for i, u in enumerate(usernames):
                        if self.task and self.task.done():
                            break

                        progress_cb(f"📥 Processing user {i+1}/{len(usernames)}: {u}")

                        # Save state before starting each user
                        self.save_scrape_state(
                            mode="batch",
                            usernames=usernames,
                            current_index=i,
                            current_username=u,
                            tweets_scraped=total_tweets,
                            settings={
                                "start_date": start,
                                "end_date": end,
                                "export_format": fmt,
                                "save_dir": save_dir,
                            },
                            file_path=self.file_path,
                        )

                        try:
                            out, cnt, seen_ids = await scrape_tweets(
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
                                cookie_expired_callback=cookie_expired_cb,
                                save_dir=save_dir,
                                break_settings=break_settings,
                            )

                            total_tweets += cnt
                            progress_cb(f"✅ {cnt} tweets saved for {u}")

                        except CookieExpiredError:
                            self.show_cookie_expired_dialog()
                            # Wait for cookies, then continue with same user
                            while self.paused_for_cookies:
                                await asyncio.sleep(0.5)
                            # Retry this user
                            i -= 1
                            continue

                        except NetworkError as e:
                            self.show_network_error_dialog(str(e))
                            if not self.paused_for_network:
                                break  # User cancelled
                            # If user chose retry, continue
                            i -= 1
                            continue

                    # Clear state on successful completion
                    self.state_manager.clear_state()
                    return [], total_tweets

                self.task = loop.create_task(batch_task())
                output, total = loop.run_until_complete(self.task)
                self.log(f"🎉 Batch complete! Total tweets: {total}")
                messagebox.showinfo(
                    "Batch Complete", f"Successfully scraped {total} tweets!"
                )

            else:
                _, user, kws = target

                # Save initial state
                self.save_scrape_state(
                    mode="single",
                    current_username=user,
                    keywords=kws,
                    tweets_scraped=0,
                    settings={
                        "start_date": start,
                        "end_date": end,
                        "export_format": fmt,
                        "save_dir": save_dir,
                        "use_and": (self.op_var.get() == "AND"),
                    },
                )

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
                        cookie_expired_callback=cookie_expired_cb,
                        save_dir=save_dir,
                        break_settings=break_settings,
                    )
                )
                output, total, seen_ids = loop.run_until_complete(self.task)

                # Clear state on success
                self.state_manager.clear_state()

                self.log(
                    f"🎉 Complete! {total} tweets saved to: {os.path.basename(output)}"
                )
                messagebox.showinfo("Success", f"✅ {total} tweets saved to:\n{output}")

        except asyncio.CancelledError:
            self.log("⚠️ Scraping cancelled by user")
            self.count_lbl.config(text="Cancelled", foreground="orange")

        except CookieExpiredError as e:
            self.log(f"🔑 Cookie expired: {e}")
            messagebox.showwarning(
                "Cookies Expired",
                "Your session has been saved.\n"
                "Update your cookies and click 'Start' to resume.",
            )

        except NetworkError as e:
            self.log(f"🔌 Network error: {e}")
            messagebox.showwarning(
                "Network Error",
                "Your progress has been saved.\n"
                "Check your connection and click 'Start' to resume.",
            )

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
        current_row = self.create_break_settings_section(current_row)
        current_row = self.create_cookie_section(current_row)
        current_row = self.create_controls_section(current_row)
        self.create_status_section(current_row)

    def create_header_section(self, row):
        header_frame = ttk.Frame(self.main_tab)
        header_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        header_frame.columnconfigure(1, weight=1)

        try:
            logo_file = resource_path(os.path.join("assets", "logo.png"))
            img = Image.open(logo_file).resize((50, 50), Image.Resampling.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            ttk.Label(header_frame, image=self.logo_img).grid(
                row=0, column=0, padx=(0, 10)
            )
        except Exception:
            pass

        title_frame = ttk.Frame(header_frame)
        title_frame.grid(row=0, column=1, sticky="w")

        ttk.Label(
            title_frame, text="Chi Tweet Scraper", font=("Segoe UI", 14, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_frame,
            text="Extract tweets with ease",
            font=("Segoe UI", 8),
            foreground="gray",
        ).grid(row=1, column=0, sticky="w")

        return row + 1

    def create_config_section(self, row):
        config_frame = ttk.LabelFrame(
            self.main_tab,
            text="Configuration",
            padding="8",
        )
        config_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        config_frame.columnconfigure(1, weight=1)

        # Row 0: Export format and Save folder in same row
        ttk.Label(config_frame, text="Export:").grid(
            row=0, column=0, sticky="w", pady=3
        )

        format_folder_frame = ttk.Frame(config_frame)
        format_folder_frame.grid(row=0, column=1, sticky="ew", pady=3)
        format_folder_frame.columnconfigure(1, weight=1)

        self.format_var = tk.StringVar(value="Excel")
        format_combo = ttk.Combobox(
            format_folder_frame,
            textvariable=self.format_var,
            values=["Excel", "CSV"],
            state="readonly",
            width=10,
        )
        format_combo.grid(row=0, column=0, padx=(0, 10))

        # Save folder in same row
        ttk.Entry(
            format_folder_frame, textvariable=self.save_dir, state="readonly"
        ).grid(row=0, column=1, sticky="ew", padx=(0, 5))
        ttk.Button(
            format_folder_frame, text="📁", command=self.choose_folder, width=3
        ).grid(row=0, column=2)

        # Row 1: Batch mode
        self.batch_var = tk.BooleanVar(value=False)
        batch_frame = ttk.Frame(config_frame)
        batch_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))

        batch_check = ttk.Checkbutton(
            batch_frame,
            text="Batch mode",
            variable=self.batch_var,
            command=self.toggle_batch,
        )
        batch_check.grid(row=0, column=0, sticky="w")

        self.file_btn = ttk.Button(
            batch_frame, text="Select File", command=self.select_file, state="disabled"
        )
        self.file_btn.grid(row=0, column=1, padx=(10, 0))

        return row + 1

    def create_search_section(self, row):
        search_frame = ttk.LabelFrame(
            self.main_tab,
            text="Search Parameters",
            padding="8",
        )
        search_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        search_frame.columnconfigure(1, weight=1)

        # Row 0: Search mode
        ttk.Label(search_frame, text="Mode:").grid(row=0, column=0, sticky="w", pady=3)
        self.mode_var = tk.StringVar(value="Username")
        self.mode_menu = ttk.Combobox(
            search_frame,
            textvariable=self.mode_var,
            values=["Username", "Keywords"],
            state="readonly",
            width=15,
        )
        self.mode_menu.grid(row=0, column=1, sticky="w", pady=3)
        self.mode_menu.bind("<<ComboboxSelected>>", self.update_mode)

        # Row 1: Username/Keywords input
        self.username_label = ttk.Label(search_frame, text="Username:")
        self.username_label.grid(row=1, column=0, sticky="w", pady=3)

        input_frame = ttk.Frame(search_frame)
        input_frame.grid(row=1, column=1, sticky="ew", pady=3)
        input_frame.columnconfigure(0, weight=1)

        self.username_entry = ttk.Entry(input_frame)
        self.username_entry.grid(row=0, column=0, sticky="ew")

        self.keyword_label = ttk.Label(search_frame, text="Keywords:")
        self.keyword_entry = ttk.Entry(input_frame)

        # For keywords mode
        self.op_label = ttk.Label(search_frame, text="Operator:")
        self.op_var = tk.StringVar(value="OR")
        self.op_menu = ttk.Combobox(
            input_frame,
            textvariable=self.op_var,
            values=["OR", "AND"],
            state="readonly",
            width=8,
        )

        # Row 2: Date range
        # Row 2: Date and Time range
        date_frame = ttk.Frame(search_frame)
        date_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        date_frame.columnconfigure(1, weight=1)
        date_frame.columnconfigure(5, weight=1)

        # Start Date
        ttk.Label(date_frame, text="From:", font=("Segoe UI", 8)).grid(
            row=0, column=0, sticky="w", padx=(0, 3)
        )
        self.start_entry = ttk.Entry(date_frame, width=10)
        self.start_entry.grid(row=0, column=1, sticky="ew", padx=(0, 3))

        # Start Time (optional)
        self.start_time_entry = ttk.Entry(date_frame, width=9)
        self.start_time_entry.grid(row=0, column=2, sticky="ew", padx=(0, 10))
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.config(foreground='gray')
        self.start_time_entry.bind('<FocusIn>', lambda e: self._on_time_focus_in(e, "00:00:00"))
        self.start_time_entry.bind('<FocusOut>', lambda e: self._validate_time_entry(e))

        # End Date
        ttk.Label(date_frame, text="To:", font=("Segoe UI", 8)).grid(
            row=0, column=3, sticky="w", padx=(0, 3)
        )
        self.end_entry = ttk.Entry(date_frame, width=10)
        self.end_entry.grid(row=0, column=4, sticky="ew", padx=(0, 3))

        # End Time (optional)
        self.end_time_entry = ttk.Entry(date_frame, width=9)
        self.end_time_entry.grid(row=0, column=5, sticky="ew")
        self.end_time_entry.insert(0, "23:59:59")
        self.end_time_entry.config(foreground='gray')
        self.end_time_entry.bind('<FocusIn>', lambda e: self._on_time_focus_in(e, "23:59:59"))
        self.end_time_entry.bind('<FocusOut>', lambda e: self._validate_time_entry(e))

        ttk.Label(
            search_frame,
            text="Format: YYYY-MM-DD HH:MM:SS (time is optional, leave as default for full day)",
            font=("Segoe UI", 7),
            foreground="gray",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        return row + 1

    def create_break_settings_section(self, row):
        """Create the break settings section with checkbox and configuration options."""
        break_frame = ttk.LabelFrame(
            self.main_tab,
            text="Rate Limit Prevention",
            padding="8",
        )
        break_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        break_frame.columnconfigure(1, weight=1)

        # Row 0: Enable checkbox
        self.enable_breaks_var = tk.BooleanVar(value=False)
        self.break_checkbox = ttk.Checkbutton(
            break_frame,
            text="Enable random breaks",
            variable=self.enable_breaks_var,
            command=self.toggle_break_settings,
        )
        self.break_checkbox.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))

        # Row 1: Interval and Duration in one row
        settings_frame = ttk.Frame(break_frame)
        settings_frame.grid(row=1, column=0, columnspan=2, sticky="ew")

        ttk.Label(settings_frame, text="Every:", font=("Segoe UI", 8)).grid(
            row=0, column=0, sticky="w", padx=(0, 3)
        )

        self.tweet_interval_var = tk.StringVar(value="100")
        self.tweet_interval_spinbox = ttk.Spinbox(
            settings_frame,
            from_=50,
            to=500,
            increment=50,
            textvariable=self.tweet_interval_var,
            width=8,
            state="disabled",
        )
        self.tweet_interval_spinbox.grid(row=0, column=1, padx=(0, 3))
        ttk.Label(
            settings_frame, text="tweets", font=("Segoe UI", 8), foreground="gray"
        ).grid(row=0, column=2, padx=(0, 10))

        ttk.Label(settings_frame, text="Break:", font=("Segoe UI", 8)).grid(
            row=0, column=3, sticky="w", padx=(0, 3)
        )

        self.min_break_var = tk.StringVar(value="5")
        self.min_break_spinbox = ttk.Spinbox(
            settings_frame,
            from_=1,
            to=30,
            increment=1,
            textvariable=self.min_break_var,
            width=6,
            state="disabled",
        )
        self.min_break_spinbox.grid(row=0, column=4, padx=(0, 3))

        ttk.Label(
            settings_frame, text="-", font=("Segoe UI", 8), foreground="gray"
        ).grid(row=0, column=5, padx=2)

        self.max_break_var = tk.StringVar(value="10")
        self.max_break_spinbox = ttk.Spinbox(
            settings_frame,
            from_=1,
            to=30,
            increment=1,
            textvariable=self.max_break_var,
            width=6,
            state="disabled",
        )
        self.max_break_spinbox.grid(row=0, column=6, padx=(0, 3))

        ttk.Label(
            settings_frame, text="min", font=("Segoe UI", 8), foreground="gray"
        ).grid(row=0, column=7)

        return row + 1

    def toggle_break_settings(self):
        """Enable or disable break setting controls based on checkbox state."""
        state = "normal" if self.enable_breaks_var.get() else "disabled"
        self.tweet_interval_spinbox.config(state=state)
        self.min_break_spinbox.config(state=state)
        self.max_break_spinbox.config(state=state)

    def create_cookie_section(self, row):
        self.cookie_expanded = tk.BooleanVar(value=False)

        cookie_frame = ttk.LabelFrame(
            self.main_tab,
            text="Twitter Cookies",
            padding="8",
        )
        cookie_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        cookie_frame.columnconfigure(0, weight=1)

        toggle_frame = ttk.Frame(cookie_frame)
        toggle_frame.grid(row=0, column=0, sticky="ew")

        self.cookie_toggle = ttk.Button(
            toggle_frame, text="▶ Show Cookie Input", command=self.toggle_cookie_section
        )
        self.cookie_toggle.grid(row=0, column=0, sticky="w")

        self.cookie_input_frame = ttk.Frame(cookie_frame)
        self.cookie_input_frame.columnconfigure(0, weight=1)

        ttk.Label(
            self.cookie_input_frame, text="Paste cookie JSON:", font=("Segoe UI", 8)
        ).grid(row=0, column=0, sticky="w", pady=(8, 3))

        self.cookie_text = tk.Text(
            self.cookie_input_frame,
            width=60,
            height=3,
            wrap=tk.WORD,
            font=("Consolas", 8),
        )
        self.cookie_text.grid(row=1, column=0, sticky="ew", pady=(0, 5))

        ttk.Button(
            self.cookie_input_frame, text="Save Cookies", command=self.save_cookies
        ).grid(row=2, column=0, sticky="e")

        return row + 1

    def create_controls_section(self, row):
        controls_frame = ttk.Frame(self.main_tab)
        controls_frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        controls_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(
            controls_frame, length=300, mode="indeterminate"
        )
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress.grid_remove()

        status_button_frame = ttk.Frame(controls_frame)
        status_button_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        status_button_frame.columnconfigure(0, weight=1)

        self.count_lbl = ttk.Label(
            status_button_frame,
            text="Ready to scrape",
            foreground="gray",
            font=("Segoe UI", 8),
        )
        self.count_lbl.grid(row=0, column=0, sticky="w")

        button_frame = ttk.Frame(status_button_frame)
        button_frame.grid(row=0, column=1, sticky="e")

        self.scrape_button = ttk.Button(
            button_frame, text="Start", command=self.start_scrape_thread
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
        log_frame = ttk.LabelFrame(self.main_tab, text="Activity Log", padding="6")
        log_frame.grid(row=row, column=0, sticky="nsew", pady=(0, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(
            log_frame,
            width=70,
            height=8,
            bg="#f8f9fa",
            font=("Consolas", 8),
            wrap=tk.WORD,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(log_frame, text="Clear", command=self.clear_logs).grid(
            row=1, column=0, sticky="e", pady=(3, 0)
        )

    def create_links_tab(self):
        self.links_tab.columnconfigure(0, weight=1)
        self.links_tab.rowconfigure(4, weight=1)

        container = ttk.Frame(self.links_tab)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)

        ttk.Label(
            container,
            text="Scrape tweets from a file containing tweet links (.txt or .xlsx).",
            font=("Segoe UI", 9),
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
        links_log_frame = ttk.LabelFrame(container, text="Activity Log", padding="6")
        links_log_frame.grid(row=4, column=0, sticky="nsew", pady=(10, 0))
        links_log_frame.columnconfigure(0, weight=1)
        links_log_frame.rowconfigure(0, weight=1)

        self.links_log_text = ScrolledText(
            links_log_frame,
            width=70,
            height=8,
            bg="#f8f9fa",
            font=("Consolas", 8),
            wrap=tk.WORD,
        )
        self.links_log_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(links_log_frame, text="Clear", command=self.clear_links_logs).grid(
            row=1, column=0, sticky="e", pady=(3, 0)
        )

    def toggle_cookie_section(self):
        if self.cookie_expanded.get():
            self.cookie_input_frame.grid_remove()
            self.cookie_toggle.config(text="▶ Show Cookie Input")
            self.cookie_expanded.set(False)
        else:
            self.cookie_input_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
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
            self.username_label.grid(row=1, column=0, sticky="w", pady=3)
            self.username_entry.grid(row=0, column=0, sticky="ew")
            self.keyword_label.grid_remove()
            self.keyword_entry.grid_remove()
            self.op_label.grid_remove()
            self.op_menu.grid_remove()
        else:
            self.username_label.grid_remove()
            self.username_entry.grid_remove()
            self.keyword_label.grid(row=1, column=0, sticky="w", pady=3)
            self.keyword_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
            self.op_label.grid_remove()
            self.op_menu.grid(row=0, column=1, sticky="w")
            
    def _on_time_focus_in(self, event, default):
        """Clear placeholder when time field is focused."""
        widget = event.widget
        current = widget.get()
        if current == default or widget.cget('foreground') == 'gray':
            widget.delete(0, tk.END)
            widget.config(foreground='black')

    def _validate_time_entry(self, event):
        """Validate time entry format on focus out."""
        widget = event.widget
        time_str = widget.get().strip()
        
        # Determine default based on which widget
        is_start = (widget == self.start_time_entry)
        default = "00:00:00" if is_start else "23:59:59"
        
        if not time_str:
            # Empty - use default
            widget.insert(0, default)
            widget.config(foreground='gray')
            return
        
        try:
            # Try to parse as HH:MM:SS
            datetime.strptime(time_str, "%H:%M:%S")
            widget.config(foreground='black')
        except ValueError:
            try:
                # Try HH:MM format and convert
                datetime.strptime(time_str, "%H:%M")
                widget.delete(0, tk.END)
                widget.insert(0, f"{time_str}:00")
                widget.config(foreground='black')
            except ValueError:
                # Invalid format
                widget.config(foreground='red')
                messagebox.showwarning(
                    "Invalid Time",
                    "Time must be in HH:MM:SS or HH:MM format (24-hour).\n"
                    "Example: 14:30:00 or 14:30",
                    parent=self.root
                )
                widget.delete(0, tk.END)
                widget.insert(0, default)
                widget.config(foreground='gray')        
                
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

    def get_break_settings(self):
        """Get the current break settings from the GUI."""
        if not self.enable_breaks_var.get():
            return None

        try:
            tweet_interval = int(self.tweet_interval_var.get())
            min_break = int(self.min_break_var.get())
            max_break = int(self.max_break_var.get())

            # Validate settings
            if min_break > max_break:
                messagebox.showwarning(
                    "Invalid Settings",
                    "Minimum break duration cannot be greater than maximum.",
                )
                return None

            return {
                "enabled": True,
                "tweet_interval": tweet_interval,
                "min_break_minutes": min_break,
                "max_break_minutes": max_break,
            }
        except ValueError:
            messagebox.showerror(
                "Invalid Input", "Please enter valid numbers for break settings."
            )
            return None

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
            # Get and validate time inputs
            start_time = self.start_time_entry.get().strip()
            end_time = self.end_time_entry.get().strip()
            
            # Default times if not provided or still placeholder
            if not start_time or start_time == "00:00:00" or self.start_time_entry.cget('foreground') == 'gray':
                start_time = "00:00:00"
            
            if not end_time or end_time == "23:59:59" or self.end_time_entry.cget('foreground') == 'gray':
                end_time = "23:59:59"
            
            # Validate time formats
            try:
                datetime.strptime(start_time, "%H:%M:%S")
            except ValueError:
                try:
                    # Try HH:MM format
                    datetime.strptime(start_time, "%H:%M")
                    start_time = f"{start_time}:00"
                except ValueError:
                    messagebox.showerror(
                        "Invalid Time",
                        "Start time must be in HH:MM:SS or HH:MM format.\n"
                        "Example: 14:30:00 or 14:30"
                    )
                    return
            
            try:
                datetime.strptime(end_time, "%H:%M:%S")
            except ValueError:
                try:
                    datetime.strptime(end_time, "%H:%M")
                    end_time = f"{end_time}:00"
                except ValueError:
                    messagebox.showerror(
                        "Invalid Time",
                        "End time must be in HH:MM:SS or HH:MM format.\n"
                        "Example: 23:59:59 or 23:59"
                    )
                    return
            
            # Parse full datetime
            start_dt = datetime.strptime(f"{start} {start_time}", "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(f"{end} {end_time}", "%Y-%m-%d %H:%M:%S")
            today = datetime.now()

            # Validate future dates
            if end_dt > today:
                response = messagebox.askyesno(
                    "Future Date",
                    f"End date/time is in the future: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    "Use current date/time instead?",
                    icon='warning'
                )
                if response:
                    end_dt = today
                    end = today.strftime("%Y-%m-%d")
                    end_time = today.strftime("%H:%M:%S")
                    self.end_entry.delete(0, tk.END)
                    self.end_entry.insert(0, end)
                    self.end_time_entry.delete(0, tk.END)
                    self.end_time_entry.insert(0, end_time)
                    self.end_time_entry.config(foreground='black')
                else:
                    return

            if start_dt >= end_dt:
                messagebox.showerror(
                    "Invalid Range",
                    f"Start date/time must be before end date/time.\n\n"
                    f"Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"End: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return
            
            # Format for Twitter API (YYYY-MM-DD_HH:MM:SS)
            start = start_dt.strftime("%Y-%m-%d_%H:%M:%S")
            end = end_dt.strftime("%Y-%m-%d_%H:%M:%S")
            
            # Store datetime objects for progress estimation
            self.start_dt = start_dt
            self.end_dt = end_dt
                
        except ValueError as e:
            messagebox.showerror(
                "Invalid Date/Time",
                f"Please check your date and time format:\n"
                f"Date: YYYY-MM-DD\n"
                f"Time: HH:MM:SS (optional)\n\n"
                f"Error: {str(e)}"
            )
            return
        
        if not os.path.isdir(save_dir):
            messagebox.showerror(
                "Invalid Path", f"Save directory not found:\n{save_dir}"
            )
            return

        # Get break settings
        break_settings = self.get_break_settings()
        if self.enable_breaks_var.get() and break_settings is None:
            return  # Invalid settings, error already shown

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
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress.start(30)
        self.count_lbl.config(text="Initializing scraper...", foreground="blue")
        self.clear_logs()
        self.log("🚀 Starting scrape operation...")

        if break_settings:
            self.log(
                f"⏸️ Breaks enabled: Every {break_settings['tweet_interval']} tweets, "
                f"{break_settings['min_break_minutes']}-{break_settings['max_break_minutes']} min"
            )

        threading.Thread(
            target=self._run_scrape,
            args=(target, start, end, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def _run_scrape(self, target, start, end, fmt, save_dir, break_settings):
        """Enhanced scraping with intelligent error handling and resumption."""

        def progress_cb(msg):
            if isinstance(msg, str):
                self.log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        def cookie_expired_cb(error_msg):
            """Called when cookies expire - pause and request new cookies."""
            self.log(f"🔑 Authentication expired: {error_msg}")
            self.paused_for_cookies = True
            
            # Schedule cookie dialog on main thread
            self.root.after(0, self._show_cookie_expired_dialog_with_resume)
            
            # Wait for cookies to be updated
            import time
            while self.paused_for_cookies:
                time.sleep(0.5)
                if self.task and self.task.done():
                    break

        def network_error_cb(error_msg):
            """Called when network fails - pause and wait for reconnection."""
            self.log(f"🔌 Network error: {error_msg}")
            self.paused_for_network = True
            
            # Schedule network dialog on main thread
            self.root.after(0, lambda: self._show_network_error_dialog_with_resume(error_msg))
            
            # Wait for network to be restored
            import time
            while self.paused_for_network:
                time.sleep(0.5)
                if self.task and self.task.done():
                    break

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            if target[0] == "batch":

                async def batch_task():
                    total_tweets = 0
                    usernames = target[1]

                    for i, u in enumerate(usernames):
                        if self.task and self.task.done():
                            break

                        progress_cb(f"📥 Processing user {i+1}/{len(usernames)}: {u}")

                        # Save state before each user
                        self.save_scrape_state(
                            mode="batch",
                            usernames=usernames,
                            current_index=i,
                            current_username=u,
                            tweets_scraped=total_tweets,
                            settings={
                                "start_date": start,
                                "end_date": end,
                                "export_format": fmt,
                                "save_dir": save_dir,
                            },
                            file_path=self.file_path,
                        )

                        retry_user = True
                        while retry_user:
                            try:
                                out, cnt, seen_ids = await scrape_tweets(
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
                                    cookie_expired_callback=cookie_expired_cb,
                                    network_error_callback=network_error_cb,
                                    save_dir=save_dir,
                                    break_settings=break_settings,
                                )

                                total_tweets += cnt
                                progress_cb(f"✅ {cnt} tweets saved for {u}")
                                retry_user = False

                            except CookieExpiredError:
                                cookie_expired_cb(f"Cookies expired while scraping @{u}")
                                # Loop will retry after cookies updated

                            except NetworkError as e:
                                network_error_cb(str(e))
                                # Loop will retry after network restored
                            
                            except EmptyPagePromptException as e:
                                # Ask user if they want to continue
                                should_continue = self._show_empty_page_prompt(u, total_tweets)
                                if not should_continue:
                                    retry_user = False
                                    progress_cb(f"⏩ Skipping rest of @{u} due to empty pages")

                    # Clear state on success
                    self.state_manager.clear_state()
                    return [], total_tweets

                self.task = loop.create_task(batch_task())
                output, total = loop.run_until_complete(self.task)
                self.log(f"🎉 Batch complete! Total tweets: {total}")
                messagebox.showinfo(
                    "Batch Complete", f"Successfully scraped {total} tweets!"
                )

            else:
                _, user, kws = target

                # Save initial state
                self.save_scrape_state(
                    mode="single",
                    current_username=user,
                    keywords=kws,
                    tweets_scraped=0,
                    settings={
                        "start_date": start,
                        "end_date": end,
                        "export_format": fmt,
                        "save_dir": save_dir,
                        "use_and": (self.op_var.get() == "AND"),
                    },
                )

                retry_scrape = True
                while retry_scrape:
                    try:
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
                                cookie_expired_callback=cookie_expired_cb,
                                network_error_callback=network_error_cb,
                                save_dir=save_dir,
                                break_settings=break_settings,
                            )
                        )
                        output, total, seen_ids = loop.run_until_complete(self.task)

                        # Clear state on success
                        self.state_manager.clear_state()
                        retry_scrape = False

                        self.log(
                            f"🎉 Complete! {total} tweets saved to: {os.path.basename(output)}"
                        )
                        messagebox.showinfo("Success", f"✅ {total} tweets saved to:\n{output}")

                    except CookieExpiredError:
                        cookie_expired_cb("Cookies expired during scraping")
                        # Loop will retry after cookies updated

                    except NetworkError as e:
                        network_error_cb(str(e))
                        # Loop will retry after network restored
                    
                    except EmptyPagePromptException as e:
                        should_continue = self._show_empty_page_prompt(user or "keywords", None)
                        if not should_continue:
                            retry_scrape = False
                            self.log("⏹️ Scraping stopped by user decision")

                    except asyncio.CancelledError:
                        self.log("⚠️ Scraping cancelled by user")
                        self.count_lbl.config(text="Cancelled", foreground="orange")
                        retry_scrape = False

                    except Exception as e:
                        self.log(f"❌ Unexpected error: {e}")
                        self.count_lbl.config(text="Error occurred", foreground="red")
                        messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")
                        retry_scrape = False

                    finally:
                        self.progress.stop()
                        self.progress.grid_remove()
                        self.scrape_button.config(state="normal")
                        self.stop_btn.config(state="disabled")
                        self.count_lbl.config(text="Ready to scrape", foreground="gray")
                        self.paused_for_cookies = False
                        self.paused_for_network = False
                        self.task = None
                        self.current_task_type = None

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

        # Get break settings
        break_settings = self.get_break_settings()
        if self.enable_breaks_var.get() and break_settings is None:
            return

        # UI state changes
        self.current_task_type = "links"
        self.links_scrape_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress.start(30)
        self.count_lbl.config(text="Initializing link scraper...", foreground="blue")
        self.clear_links_logs()
        self.links_log("🚀 Starting link-based scrape operation...")

        if break_settings:
            self.links_log(
                f"⏸️ Breaks enabled: Every {break_settings['tweet_interval']} tweets, "
                f"{break_settings['min_break_minutes']}-{break_settings['max_break_minutes']} min"
            )

        threading.Thread(
            target=self._run_links,
            args=(links_path, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def _run_links(self, links_path, fmt, save_dir, break_settings):
        def progress_cb(msg):
            if isinstance(msg, str):
                self.links_log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            async def links_task():
                out, cnt, failed, processed = await scrape_tweet_links_file(
                    file_path=links_path,
                    export_format=fmt,
                    save_dir=save_dir,
                    progress_callback=progress_cb,
                    should_stop_callback=lambda: (
                        self.task.done() if self.task else False
                    ),
                    break_settings=break_settings,
                )
                return out, cnt, failed

            self.task = loop.create_task(links_task())
            output, total, failed = loop.run_until_complete(self.task)

            self.links_log(
                f"🎉 Complete! {total} tweets saved to: {os.path.basename(output)}"
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
        guide_text = """Welcome to Chi Tweet Scraper! Here's a step-by-step guide:

1. Setting Up Cookies (Required):
• Install "cookie-editor" browser extension
• Log in to Twitter in your browser
• Export cookies as JSON and paste them

2. Configuration:
• Choose export format (Excel/CSV)
• Select save folder
• Use batch mode for multiple usernames

3. Search Parameters:
• Search by username or keywords
• Enter date range (YYYY-MM-DD)

4. Rate Limit Prevention (Optional):
• Enable random breaks to avoid rate limits
• Configure tweet interval and break duration
• Breaks shown distinctly in Activity Log

5. Start Scraping:
• Click "Start" to begin
• Monitor progress in Activity Log
• Use "Stop" if needed

Tips:
• Use batch mode for multiple users
• Narrow date ranges for better results
• Enable breaks for long sessions

Installation Guide:
https://youtu.be/RKX2sgQVgBg

How to Use:
https://youtu.be/AbdpX6QZLm4
"""

        guide_window = tk.Toplevel(self.root)
        guide_window.title("User Guide")
        guide_window.geometry("500x500")
        guide_window.resizable(False, False)
        guide_window.transient(self.root)
        guide_window.grab_set()

        guide_window.update_idletasks()
        x = (guide_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (guide_window.winfo_screenheight() // 2) - (500 // 2)
        guide_window.geometry(f"500x500+{x}+{y}")

        text_frame = ttk.Frame(guide_window, padding="20")
        text_frame.pack(fill="both", expand=True)

        text_widget = ScrolledText(text_frame, wrap=tk.WORD, font=("Segoe UI", 9))
        text_widget.pack(fill="both", expand=True)

        text_widget.insert("1.0", guide_text)

        def add_hyperlink(url, start, end):
            text_widget.tag_add(url, start, end)
            text_widget.tag_config(url, foreground="blue", underline=1)
            text_widget.tag_bind(url, "<Button-1>", lambda e: webbrowser.open(url))

        start_idx = text_widget.search("https://youtu.be/RKX2sgQVgBg", "1.0", tk.END)
        if start_idx:
            end_idx = f"{start_idx}+{len('https://youtu.be/RKX2sgQVgBg')}c"
            add_hyperlink("https://youtu.be/RKX2sgQVgBg", start_idx, end_idx)

        start_idx = text_widget.search("https://youtu.be/AbdpX6QZLm4", "1.0", tk.END)
        if start_idx:
            end_idx = f"{start_idx}+{len('https://youtu.be/AbdpX6QZLm4')}c"
            add_hyperlink("https://youtu.be/AbdpX6QZLm4", start_idx, end_idx)

        text_widget.config(state="disabled")

        ttk.Button(guide_window, text="Close", command=guide_window.destroy).pack(
            pady=(0, 20)
        )


if __name__ == "__main__":
    cookies_dir = resource_path("cookies")
    exports_dir = resource_path(os.path.join("data", "exports"))
    os.makedirs(cookies_dir, exist_ok=True)
    os.makedirs(exports_dir, exist_ok=True)

    root = tk.Tk()

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
