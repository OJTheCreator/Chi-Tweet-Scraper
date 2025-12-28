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

        # Split date and time for start date
        start_full = settings.get("start_date", "")
        if "_" in start_full:
            start_date, start_time = start_full.split("_")
        else:
            start_date = start_full
            start_time = "00:00:00"

        self.start_entry.delete(0, tk.END)
        self.start_entry.insert(0, start_date)
        self.start_time_entry.delete(0, tk.END)
        self.start_time_entry.insert(0, start_time)
        self.start_time_entry.config(foreground="black")

        # Split date and time for end date
        end_full = settings.get("end_date", "")
        if "_" in end_full:
            end_date, end_time = end_full.split("_")
        else:
            end_date = end_full
            end_time = "23:59:59"

        self.end_entry.delete(0, tk.END)
        self.end_entry.insert(0, end_date)
        self.end_time_entry.delete(0, tk.END)
        self.end_time_entry.insert(0, end_time)
        self.end_time_entry.config(foreground="black")

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

        # Split date and time for start date
        start_full = settings.get("start_date", "")
        if "_" in start_full:
            start_date, start_time = start_full.split("_")
        else:
            start_date = start_full
            start_time = "00:00:00"

        self.start_entry.delete(0, tk.END)
        self.start_entry.insert(0, start_date)
        self.start_time_entry.delete(0, tk.END)
        self.start_time_entry.insert(0, start_time)
        self.start_time_entry.config(foreground="black")

        # Split date and time for end date
        end_full = settings.get("end_date", "")
        if "_" in end_full:
            end_date, end_time = end_full.split("_")
        else:
            end_date = end_full
            end_time = "23:59:59"

        self.end_entry.delete(0, tk.END)
        self.end_entry.insert(0, end_date)
        self.end_time_entry.delete(0, tk.END)
        self.end_time_entry.insert(0, end_time)
        self.end_time_entry.config(foreground="black")

        username = state.get("current_username")
        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(0, username)

        # Restore keywords if present
        keywords = state.get("keywords")
        if keywords:
            self.mode_var.set("Keywords")
            self.update_mode()
            self.keyword_entry.delete(0, tk.END)
            self.keyword_entry.insert(0, ", ".join(keywords))
            use_and = settings.get("use_and", False)
            self.op_var.set("AND" if use_and else "OR")
        else:
            self.mode_var.set("Username")
            self.update_mode()

        self.log(f"🔄 Resuming scrape for @{username}")

        # Start scraping with resume state
        self.start_single_scrape_with_resume(settings, state)

    def resume_links_scrape(self, state):
        """Resume link scraping from saved state."""
        # Switch to links tab
        self.notebook.select(1)

        # Restore settings
        settings = state.get("settings", {})
        self.links_file_path = state.get("links_file_path")
        self.links_file_var.set(self.links_file_path)

        # Restore format
        self.format_var.set(settings.get("export_format", "Excel"))
        self.save_dir.set(settings.get("save_dir", self.save_dir.get()))

        self.links_log(f"🔄 Resuming link scrape from saved position")

        # Start scraping with resume state
        self.start_links_scrape_with_resume(settings, state)

    def start_batch_scrape_with_resume(self, remaining_usernames, settings, state):
        """Resume batch scraping with remaining users."""
        all_usernames = state.get("usernames", [])
        current_index = state.get("current_index", 0)

        self.log(
            f"🔄 Resuming batch scrape from user {current_index + 1}/{len(all_usernames)}"
        )

        # Rebuild the target tuple with remaining users
        target = ("batch", remaining_usernames)

        # Extract settings
        start = settings.get("start_date")
        end = settings.get("end_date")
        fmt = settings.get("export_format", "excel").lower()
        save_dir = settings.get("save_dir", self.save_dir.get())

        # Get break settings from current UI state (user may have changed them)
        break_settings = self.get_break_settings()

        # Validate we have what we need
        if not start or not end:
            messagebox.showerror(
                "Resume Error",
                "Cannot resume: missing date information in saved state.",
            )
            self.state_manager.clear_state()
            return

        if not remaining_usernames:
            self.log("✅ All users already processed!")
            messagebox.showinfo(
                "Resume Complete", "All users in the batch have already been scraped."
            )
            self.state_manager.clear_state()
            return

        # Update UI state
        self.current_task_type = "main"
        self.scrape_button.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress.start(30)
        self.count_lbl.config(text="Resuming batch scrape...", foreground="blue")

        # Log what we're resuming
        total_tweets = state.get("tweets_scraped", 0)
        self.log(
            f"📊 Progress so far: {total_tweets} tweets from {current_index} users"
        )
        self.log(f"📋 Remaining: {len(remaining_usernames)} users to scrape")

        if break_settings:
            self.log(
                f"⏸️ Breaks enabled: Every {break_settings['tweet_interval']} tweets, "
                f"{break_settings['min_break_minutes']}-{break_settings['max_break_minutes']} min"
            )

        # Start scraping in background thread
        threading.Thread(
            target=self._run_scrape,
            args=(target, start, end, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def start_single_scrape_with_resume(self, settings, state):
        """Resume single user scraping from saved state."""
        username = state.get("current_username")
        keywords = state.get("keywords")
        tweets_scraped = state.get("tweets_scraped", 0)

        if not username and not keywords:
            messagebox.showerror(
                "Resume Error",
                "Cannot resume: missing username/keywords in saved state.",
            )
            self.state_manager.clear_state()
            return

        self.log(f"🔄 Resuming scrape for @{username if username else 'keywords'}")
        self.log(f"📊 Progress so far: {tweets_scraped} tweets")

        # Extract settings
        start = settings.get("start_date")
        end = settings.get("end_date")
        fmt = settings.get("export_format", "excel").lower()
        save_dir = settings.get("save_dir", self.save_dir.get())
        use_and = settings.get("use_and", False)

        # Validate we have what we need
        if not start or not end:
            messagebox.showerror(
                "Resume Error",
                "Cannot resume: missing date information in saved state.",
            )
            self.state_manager.clear_state()
            return

        # Rebuild the target tuple
        target = ("single", username, keywords)

        # Get break settings from current UI state
        break_settings = self.get_break_settings()

        # Update UI state
        self.current_task_type = "main"
        self.scrape_button.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress.start(30)
        self.count_lbl.config(text="Resuming scrape...", foreground="blue")

        if keywords:
            self.log(
                f"🔍 Keywords: {', '.join(keywords)} ({settings.get('operator', 'OR')})"
            )

        if break_settings:
            self.log(
                f"⏸️ Breaks enabled: Every {break_settings['tweet_interval']} tweets, "
                f"{break_settings['min_break_minutes']}-{break_settings['max_break_minutes']} min"
            )

        # Start scraping in background thread
        threading.Thread(
            target=self._run_scrape,
            args=(target, start, end, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def start_links_scrape_with_resume(self, settings, state):
        """Resume link scraping from saved state."""
        links_file_path = state.get("links_file_path")
        tweets_scraped = state.get("tweets_scraped", 0)
        current_index = state.get("current_index", 0)

        if not links_file_path:
            messagebox.showerror(
                "Resume Error", "Cannot resume: missing links file path in saved state."
            )
            self.state_manager.clear_state()
            return

        if not os.path.exists(links_file_path):
            messagebox.showerror(
                "Resume Error",
                f"Cannot resume: links file not found:\n{links_file_path}",
            )
            self.state_manager.clear_state()
            return

        self.links_log(f"🔄 Resuming link scrape from saved position")
        self.links_log(
            f"📊 Progress so far: {tweets_scraped} tweets from {current_index} links"
        )

        # Restore settings
        fmt = settings.get("export_format", "excel").lower()
        save_dir = settings.get("save_dir", self.save_dir.get())

        # Set the file path in the UI
        self.links_file_path = links_file_path
        self.links_file_var.set(links_file_path)

        # Get break settings from current UI state
        break_settings = self.get_break_settings()

        # Update UI state
        self.current_task_type = "links"
        self.links_scrape_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.progress.start(30)
        self.count_lbl.config(text="Resuming link scrape...", foreground="blue")

        if break_settings:
            self.links_log(
                f"⏸️ Breaks enabled: Every {break_settings['tweet_interval']} tweets, "
                f"{break_settings['min_break_minutes']}-{break_settings['max_break_minutes']} min"
            )

        # Start scraping in background thread
        threading.Thread(
            target=self._run_links,
            args=(links_file_path, fmt, save_dir, break_settings),
            daemon=True,
        ).start()

    def _show_cookie_expired_dialog_with_resume(self):
        """Show modal dialog for expired cookies that blocks until cookies are updated."""
        cookie_window = tk.Toplevel(self.root)
        cookie_window.title("🔑 Authentication Required")
        cookie_window.geometry("550x500")
        cookie_window.resizable(False, False)
        cookie_window.transient(self.root)
        cookie_window.grab_set()
        cookie_window.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent closing

        # Center window
        cookie_window.update_idletasks()
        x = (cookie_window.winfo_screenwidth() // 2) - 275
        y = (cookie_window.winfo_screenheight() // 2) - 250
        cookie_window.geometry(f"550x500+{x}+{y}")

        main_frame = ttk.Frame(cookie_window, padding="20")
        main_frame.pack(fill="both", expand=True)

        # Warning header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill="x", pady=(0, 15))

        ttk.Label(
            header_frame,
            text="⚠️ Authentication Expired",
            font=("Segoe UI", 16, "bold"),
            foreground="#ff6b35",
        ).pack()

        # Status message
        status_text = tk.Text(
            main_frame,
            height=4,
            wrap=tk.WORD,
            font=("Segoe UI", 9),
            bg="#fff3cd",
            relief="flat",
            padx=10,
            pady=10,
        )
        status_text.pack(fill="x", pady=(0, 15))
        status_text.insert(
            "1.0",
            "Your Twitter session has expired. Scraping is paused.\n\n"
            "Your progress has been automatically saved.\n"
            "Update your cookies below to continue from where you left off.",
        )
        status_text.config(state="disabled")

        # Instructions
        ttk.Label(
            main_frame,
            text="📋 How to get new cookies:",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 5))

        instructions = (
            "1. Open Twitter/X.com in your browser and log in\n"
            "2. Open the cookie-editor extension\n"
            "3. Click 'Export' → Copy cookies as JSON\n"
            "4. Paste the JSON below and click 'Update & Resume'"
        )

        instructions_label = ttk.Label(
            main_frame,
            text=instructions,
            font=("Segoe UI", 8),
            foreground="gray",
            justify="left",
        )
        instructions_label.pack(anchor="w", pady=(0, 10))

        # Cookie input
        ttk.Label(
            main_frame, text="Paste new cookie JSON:", font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 5))

        cookie_frame = ttk.Frame(main_frame)
        cookie_frame.pack(fill="both", expand=True, pady=(0, 10))

        cookie_text = ScrolledText(
            cookie_frame, wrap=tk.WORD, font=("Consolas", 8), height=8
        )
        cookie_text.pack(fill="both", expand=True)

        # Status feedback
        feedback_label = ttk.Label(
            main_frame, text="", font=("Segoe UI", 9), foreground="gray"
        )
        feedback_label.pack(pady=(5, 10))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        def save_and_resume():
            raw = cookie_text.get("1.0", tk.END).strip()
            if not raw:
                feedback_label.config(
                    text="❌ Please paste cookie JSON first", foreground="red"
                )
                return

            feedback_label.config(text="⏳ Validating cookies...", foreground="blue")
            cookie_window.update()

            from src.create_cookie import convert_editthiscookie_to_twikit_format

            if convert_editthiscookie_to_twikit_format(raw):
                feedback_label.config(
                    text="✅ Cookies validated! Resuming in 2 seconds...",
                    foreground="green",
                )
                self.log("✅ New cookies saved successfully")
                cookie_window.update()

                # Wait a moment so user sees success message
                cookie_window.after(
                    2000, lambda: self._resume_after_cookie_update(cookie_window)
                )
            else:
                feedback_label.config(
                    text="❌ Invalid cookie format. Please check and try again.",
                    foreground="red",
                )
                cookie_text.delete("1.0", tk.END)

        def cancel_scrape():
            response = messagebox.askyesno(
                "Cancel Scraping?",
                "Are you sure you want to stop scraping?\n\n"
                "Your progress has been saved and you can resume later.",
                parent=cookie_window,
            )
            if response:
                self.paused_for_cookies = False
                if self.task and not self.task.done():
                    self.task.cancel()
                cookie_window.destroy()

        ttk.Button(button_frame, text="Cancel Scraping", command=cancel_scrape).pack(
            side="left"
        )

        ttk.Button(button_frame, text="Update & Resume", command=save_and_resume).pack(
            side="right", padx=(5, 0)
        )

        # Keep window on top and focused
        cookie_window.focus_force()
        cookie_text.focus()

    def _resume_after_cookie_update(self, cookie_window):
        """Resume scraping after cookies are updated."""
        self.paused_for_cookies = False
        cookie_window.destroy()
        self.log("🔄 Resuming scraping with new authentication...")

    def _show_network_error_dialog_with_resume(self, error_msg):
        """Show dialog when network fails - waits for reconnection."""
        network_window = tk.Toplevel(self.root)
        network_window.title("🔌 Network Connection Lost")
        network_window.geometry("500x400")
        network_window.resizable(False, False)
        network_window.transient(self.root)
        network_window.grab_set()

        # Center window
        network_window.update_idletasks()
        x = (network_window.winfo_screenwidth() // 2) - 250
        y = (network_window.winfo_screenheight() // 2) - 200
        network_window.geometry(f"500x400+{x}+{y}")

        main_frame = ttk.Frame(network_window, padding="20")
        main_frame.pack(fill="both", expand=True)

        # Warning icon and message
        ttk.Label(
            main_frame,
            text="⚠️ Connection Lost",
            font=("Segoe UI", 16, "bold"),
            foreground="#ff6b35",
        ).pack(pady=(0, 10))

        # Error details
        error_frame = ttk.Frame(main_frame)
        error_frame.pack(fill="x", pady=(0, 15))

        error_text = tk.Text(
            error_frame,
            height=3,
            wrap=tk.WORD,
            font=("Segoe UI", 9),
            bg="#fff3cd",
            relief="flat",
            padx=10,
            pady=10,
        )
        error_text.pack(fill="x")
        error_text.insert(
            "1.0",
            f"Network error occurred:\n{error_msg}\n\nYour progress has been automatically saved.",
        )
        error_text.config(state="disabled")

        ttk.Label(
            main_frame,
            text="Please check your internet connection.",
            font=("Segoe UI", 10),
            justify="center",
        ).pack(pady=(10, 20))

        # Connection test status
        status_label = ttk.Label(
            main_frame,
            text="Click 'Test Connection' to check if you're back online",
            foreground="gray",
            font=("Segoe UI", 9),
        )
        status_label.pack(pady=(0, 20))

        def test_connection():
            status_label.config(text="🔄 Testing connection...", foreground="blue")
            network_window.update()

            import urllib.request

            try:
                urllib.request.urlopen("https://www.google.com", timeout=5)
                status_label.config(
                    text="✅ Connection restored! Click 'Resume' to continue.",
                    foreground="green",
                )
                resume_btn.config(state="normal")
            except:
                status_label.config(
                    text="❌ Still offline. Please check your connection and try again.",
                    foreground="red",
                )

        def resume_scraping():
            self.paused_for_network = False
            network_window.destroy()
            self.log("🔄 Resuming scraping after network restoration...")

        def cancel_scrape():
            response = messagebox.askyesno(
                "Cancel Scraping?",
                "Are you sure you want to stop scraping?\n\n"
                "Your progress has been saved and you can resume later.",
                parent=network_window,
            )
            if response:
                self.paused_for_network = False
                if self.task and not self.task.done():
                    self.task.cancel()
                network_window.destroy()

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(20, 0))

        ttk.Button(btn_frame, text="Cancel Scraping", command=cancel_scrape).pack(
            side="left"
        )

        ttk.Button(btn_frame, text="Test Connection", command=test_connection).pack(
            side="right", padx=(5, 0)
        )

        resume_btn = ttk.Button(
            btn_frame, text="Resume", command=resume_scraping, state="disabled"
        )
        resume_btn.pack(side="right")

        network_window.focus_force()

    def _show_empty_page_prompt(self, username, tweets_scraped):
        """Ask user if they want to continue after hitting empty pages."""
        message = (
            f"Hit multiple consecutive empty pages while scraping.\n\n"
            f"{'User: @' + username if username else 'Keyword search'}\n"
            f"Tweets collected so far: {tweets_scraped if tweets_scraped is not None else 'checking...'}\n\n"
            f"This could mean:\n"
            f"• Reached end of available tweets in date range\n"
            f"• Gap in tweet timeline (user didn't post for a while)\n"
            f"• Temporary Twitter API issue\n\n"
            f"Continue searching for more tweets?"
        )

        response = messagebox.askyesnocancel(
            "Continue Scraping?", message, icon="question"
        )

        if response is True:  # Yes - continue
            self.log(f"👤 User chose to continue scraping past empty pages")
            return True
        elif response is False:  # No - stop this user
            self.log(f"⏹️ User chose to stop at empty pages")
            return False
        else:  # Cancel - stop everything
            if self.task and not self.task.done():
                self.task.cancel()
            return False

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

        def progress_callback(msg):
            if isinstance(msg, str):
                self.log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        def cookie_expired_callback(error_msg):
            """Called when cookies expire - pause and request new cookies."""
            self.log(f"🔑 Authentication expired: {error_msg}")
            self.paused_for_cookies = True
            self.root.after(0, self._show_cookie_expired_dialog_with_resume)

            # Wait until cookies are updated
            import time

            while self.paused_for_cookies:
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

                        progress_callback(
                            f"📥 Processing user {i+1}/{len(usernames)}: {u}"
                        )

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

                        retry_user = True
                        while retry_user:
                            if self.task and self.task.done():
                                break

                            try:
                                out, cnt, seen_ids = await scrape_tweets(
                                    username=u,
                                    start_date=start,
                                    end_date=end,
                                    keywords=None,
                                    use_and=False,
                                    export_format=fmt,
                                    progress_callback=progress_callback,
                                    should_stop_callback=lambda: (
                                        self.task.done() if self.task else False
                                    ),
                                    cookie_expired_callback=cookie_expired_callback,
                                    network_error_callback=lambda msg: None,
                                    save_dir=save_dir,
                                    break_settings=break_settings,
                                )

                                total_tweets += cnt
                                progress_callback(f"✅ {cnt} tweets saved for {u}")
                                retry_user = False

                            except CookieExpiredError:
                                cookie_expired_callback(
                                    f"Cookies expired while scraping @{u}"
                                )

                            except NetworkError as e:
                                if self.task and self.task.done():
                                    break
                                progress_callback(f"🔌 Network error: {str(e)}")
                                await asyncio.sleep(5)

                            except EmptyPagePromptException as e:
                                should_continue = self._show_empty_page_prompt(
                                    u, total_tweets
                                )
                                if not should_continue:
                                    retry_user = False
                                    progress_callback(
                                        f"⏩ Skipping rest of @{u} due to empty pages"
                                    )

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

                async def single_task():
                    # Check for stop BEFORE authentication

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
                        if self.task and self.task.done():
                            break

                        try:
                            output, total, seen_ids = await scrape_tweets(
                                username=user,
                                start_date=start,
                                end_date=end,
                                keywords=kws,
                                use_and=(self.op_var.get() == "AND"),
                                export_format=fmt,
                                progress_callback=progress_callback,
                                should_stop_callback=lambda: (
                                    self.task.done() if self.task else False
                                ),
                                cookie_expired_callback=cookie_expired_callback,
                                network_error_callback=lambda msg: None,
                                save_dir=save_dir,
                                break_settings=break_settings,
                            )

                            # Clear state on success
                            self.state_manager.clear_state()
                            retry_scrape = False
                            return output, total, seen_ids

                        except CookieExpiredError:
                            cookie_expired_callback("Cookies expired during scraping")

                        except NetworkError as e:
                            if self.task and self.task.done():
                                break
                            progress_callback(f"🔌 Network error: {str(e)}")
                            await asyncio.sleep(5)

                        except EmptyPagePromptException as e:
                            should_continue = self._show_empty_page_prompt(
                                user or "keywords", None
                            )
                            if not should_continue:
                                retry_scrape = False
                                progress_callback("⏹️ Scraping stopped by user decision")
                                break

                    return None, 0, []

                self.task = loop.create_task(single_task())
                output, total, seen_ids = loop.run_until_complete(self.task)

                if output:
                    self.log(
                        f"🎉 Complete! {total} tweets saved to: {os.path.basename(output)}"
                    )
                    messagebox.showinfo(
                        "Success", f"✅ {total} tweets saved to:\n{output}"
                    )
                else:
                    self.log("⚠️ Scraping stopped or cancelled")

        except asyncio.CancelledError:
            self.log("⚠️ Scraping cancelled by user")
            self.count_lbl.config(text="Cancelled", foreground="orange")

        except Exception as e:
            self.log(f"❌ Unexpected error: {e}")
            self.count_lbl.config(text="Error occurred", foreground="red")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")

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

        # Row 2: Date range - FIXED VERSION
        date_frame = ttk.Frame(search_frame)
        date_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        date_frame.columnconfigure(1, weight=1)
        date_frame.columnconfigure(3, weight=1)
        date_frame.columnconfigure(5, weight=1)
        date_frame.columnconfigure(7, weight=1)

        # Start Date
        ttk.Label(date_frame, text="From:", font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w", padx=(0, 5)
        )
        self.start_entry = ttk.Entry(date_frame, width=12)
        self.start_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))

        # Start Time (optional)
        ttk.Label(date_frame, text="Time:", font=("Segoe UI", 9)).grid(
            row=0, column=2, sticky="w", padx=(0, 5)
        )
        self.start_time_entry = ttk.Entry(date_frame, width=10)
        self.start_time_entry.grid(row=0, column=3, sticky="ew", padx=(0, 15))
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.config(foreground="gray")
        self.start_time_entry.bind(
            "<FocusIn>", lambda e: self._on_time_focus_in(e, "00:00:00")
        )
        self.start_time_entry.bind("<FocusOut>", lambda e: self._validate_time_entry(e))

        # End Date
        ttk.Label(date_frame, text="To:", font=("Segoe UI", 9)).grid(
            row=0, column=4, sticky="w", padx=(0, 5)
        )
        self.end_entry = ttk.Entry(date_frame, width=12)
        self.end_entry.grid(row=0, column=5, sticky="ew", padx=(0, 5))

        # End Time (optional)
        ttk.Label(date_frame, text="Time:", font=("Segoe UI", 9)).grid(
            row=0, column=6, sticky="w", padx=(0, 5)
        )
        self.end_time_entry = ttk.Entry(date_frame, width=10)
        self.end_time_entry.grid(row=0, column=7, sticky="ew")
        self.end_time_entry.insert(0, "23:59:59")
        self.end_time_entry.config(foreground="gray")
        self.end_time_entry.bind(
            "<FocusIn>", lambda e: self._on_time_focus_in(e, "23:59:59")
        )
        self.end_time_entry.bind("<FocusOut>", lambda e: self._validate_time_entry(e))

        ttk.Label(
            search_frame,
            text="Date format: YYYY-MM-DD  |  Time is optional (HH:MM:SS or HH:MM)",
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
        if current == default or widget.cget("foreground") == "gray":
            widget.delete(0, tk.END)
            widget.config(foreground="black")

    def _validate_time_entry(self, event):
        """Validate time entry format on focus out - EMPTY IS ALLOWED."""
        widget = event.widget
        time_str = widget.get().strip()

        # Determine default based on which widget
        is_start = widget == self.start_time_entry
        default = "00:00:00" if is_start else "23:59:59"

        # If empty, set to default with gray color (optional)
        if not time_str:
            widget.insert(0, default)
            widget.config(foreground="gray")
            return

        try:
            # Try to parse as HH:MM:SS
            datetime.strptime(time_str, "%H:%M:%S")
            widget.config(foreground="black")
        except ValueError:
            try:
                # Try HH:MM format and convert
                datetime.strptime(time_str, "%H:%M")
                widget.delete(0, tk.END)
                widget.insert(0, f"{time_str}:00")
                widget.config(foreground="black")
            except ValueError:
                # Invalid format
                messagebox.showwarning(
                    "Invalid Time",
                    "Time must be in HH:MM:SS or HH:MM format (24-hour).\n"
                    "Example: 14:30:00 or 14:30\n\n"
                    "Leave empty to use full day range.",
                    parent=self.root,
                )
                widget.delete(0, tk.END)
                widget.insert(0, default)
                widget.config(foreground="gray")

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
            # Get time inputs - treat gray text as empty/default
            start_time = self.start_time_entry.get().strip()
            end_time = self.end_time_entry.get().strip()

            # Check if time is placeholder (gray) or empty - use defaults
            if (
                not start_time
                or start_time == "00:00:00"
                or self.start_time_entry.cget("foreground") == "gray"
            ):
                start_time = "00:00:00"

            if (
                not end_time
                or end_time == "23:59:59"
                or self.end_time_entry.cget("foreground") == "gray"
            ):
                end_time = "23:59:59"

            # Validate time formats if not default
            if (
                start_time != "00:00:00"
                or self.start_time_entry.cget("foreground") == "black"
            ):
                try:
                    datetime.strptime(start_time, "%H:%M:%S")
                except ValueError:
                    try:
                        datetime.strptime(start_time, "%H:%M")
                        start_time = f"{start_time}:00"
                    except ValueError:
                        messagebox.showerror(
                            "Invalid Time",
                            "Start time must be in HH:MM:SS or HH:MM format.\n"
                            "Example: 14:30:00 or 14:30",
                        )
                        return

            if (
                end_time != "23:59:59"
                or self.end_time_entry.cget("foreground") == "black"
            ):
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
                            "Example: 23:59:59 or 23:59",
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
                    icon="warning",
                )
                if response:
                    end_dt = today
                    end = today.strftime("%Y-%m-%d")
                    end_time = today.strftime("%H:%M:%S")
                    self.end_entry.delete(0, tk.END)
                    self.end_entry.insert(0, end)
                    self.end_time_entry.delete(0, tk.END)
                    self.end_time_entry.insert(0, end_time)
                    self.end_time_entry.config(foreground="black")
                else:
                    return

            if start_dt >= end_dt:
                messagebox.showerror(
                    "Invalid Range",
                    f"Start date/time must be before end date/time.\n\n"
                    f"Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"End: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
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
                f"Error: {str(e)}",
            )
            return

            # ... rest of the method continues as before
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
                    icon="warning",
                )
                if response:
                    end_dt = today
                    end = today.strftime("%Y-%m-%d")
                    end_time = today.strftime("%H:%M:%S")
                    self.end_entry.delete(0, tk.END)
                    self.end_entry.insert(0, end)
                    self.end_time_entry.delete(0, tk.END)
                    self.end_time_entry.insert(0, end_time)
                    self.end_time_entry.config(foreground="black")
                else:
                    return

            if start_dt >= end_dt:
                messagebox.showerror(
                    "Invalid Range",
                    f"Start date/time must be before end date/time.\n\n"
                    f"Start: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"End: {end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
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
                f"Error: {str(e)}",
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

    def _run_links(self, links_path, fmt, save_dir, break_settings):
        """Run link-based scraping with full error handling and resume support."""

        def progress_callback(msg):
            if isinstance(msg, str):
                self.links_log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        def cookie_expired_callback(error_msg):
            """Called when cookies expire during link scraping."""
            self.links_log(f"🔑 Authentication expired: {error_msg}")
            self.paused_for_cookies = True
            self.root.after(0, self._show_cookie_expired_dialog_with_resume)

            import time

            while self.paused_for_cookies:
                time.sleep(0.5)
                if self.task and self.task.done():
                    break

        def network_error_callback(error_msg):
            """Called when network fails during link scraping."""
            self.links_log(f"🔌 Network error: {error_msg}")
            self.paused_for_network = True
            self.root.after(
                0, lambda: self._show_network_error_dialog_with_resume(error_msg)
            )

            import time

            while self.paused_for_network:
                time.sleep(0.5)
                if self.task and self.task.done():
                    break

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:

            async def links_task():
                """Main link scraping task with retry logic."""
                retry_scrape = True

                while retry_scrape:
                    if self.task and self.task.done():
                        break

                    try:
                        # Call the actual scraper function
                        output_path, total, failed, processed = (
                            await scrape_tweet_links_file(
                                file_path=links_path,
                                export_format=fmt,
                                save_dir=save_dir,
                                progress_callback=progress_callback,
                                should_stop_callback=lambda: (
                                    self.task.done() if self.task else False
                                ),
                                cookie_expired_callback=cookie_expired_callback,
                                network_error_callback=network_error_callback,
                                break_settings=break_settings,
                            )
                        )

                        # Clear state on success
                        self.state_manager.clear_state()
                        retry_scrape = False
                        return output_path, total, failed

                    except CookieExpiredError:
                        cookie_expired_callback("Cookies expired during link scraping")
                        # Loop will retry after cookies updated

                    except NetworkError as e:
                        network_error_callback(str(e))
                        # Loop will retry after network restored

                # If we exit without success
                return None, 0, 0

            # Create and run the task
            self.task = loop.create_task(links_task())
            output, total, failed = loop.run_until_complete(self.task)

            # Success handling
            if output:
                self.links_log(f"🎉 Complete! {total} tweets saved, {failed} failed")
                self.links_log(f"📁 File: {os.path.basename(output)}")
                messagebox.showinfo(
                    "Link Scrape Complete",
                    f"✅ Successfully scraped {total} tweets!\n"
                    f"Failed/Skipped: {failed}\n\n"
                    f"Saved to: {output}",
                )
            else:
                self.links_log("⚠️ Link scraping stopped or cancelled")

        except CookieExpiredError:
            self.links_log("🔑 Cookie expired - progress saved")
            # Dialog already shown by callback

        except NetworkError as e:
            self.links_log(f"🔌 Network error - progress saved: {e}")
            # Dialog already shown by callback

        except asyncio.CancelledError:
            self.links_log("⚠️ Link scraping cancelled by user")
            self.count_lbl.config(text="Cancelled", foreground="orange")

        except Exception as e:
            self.links_log(f"❌ Unexpected error: {e}")
            self.count_lbl.config(text="Error occurred", foreground="red")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")

        finally:
            self.progress.stop()
            self.progress.grid_remove()
            self.links_scrape_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.count_lbl.config(text="Ready to scrape", foreground="gray")
            self.paused_for_cookies = False
            self.paused_for_network = False
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
        def progress_callback(msg):
            if isinstance(msg, str):
                self.links_log(msg)
            else:
                self.count_lbl.config(text=f"Tweets scraped: {msg}", foreground="green")

        def cookie_expired_callback(error_msg):
            """Called when cookies expire during link scraping."""
            self.links_log(f"🔑 Authentication expired: {error_msg}")
            self.paused_for_cookies = True
            self.root.after(0, self._show_cookie_expired_dialog_with_resume)

            import time

            while self.paused_for_cookies:
                time.sleep(0.5)
                if self.task and self.task.done():
                    break

        def network_error_callback(error_msg):
            """Called when network fails during link scraping."""
            self.links_log(f"🔌 Network error: {error_msg}")
            self.paused_for_network = True
            self.root.after(
                0, lambda: self._show_network_error_dialog_with_resume(error_msg)
            )

            import time

            while self.paused_for_network:
                time.sleep(0.5)
                if self.task and self.task.done():
                    break

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:

            async def links_task():
                out, cnt, failed, processed = await scrape_tweet_links_file(...)
                return out, cnt, failed

            self.task = loop.create_task(links_task())
            output, total, failed = loop.run_until_complete(self.task)

            self.links_log(...)
            messagebox.showinfo(...)

        except CookieExpiredError:
            self.links_log("🔑 Cookie expired - progress saved")
            # Dialog already shown by callback

        except NetworkError as e:
            self.links_log(f"🔌 Network error - progress saved: {e}")
            # Dialog already shown by callback

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
        guide_text = """🎯 CHI TWEET SCRAPER - COMPREHENSIVE USER GUIDE

    ═══════════════════════════════════════════════════════════════

    📋 TABLE OF CONTENTS
    1. Getting Started - First Time Setup
    2. Cookie Authentication (REQUIRED)
    3. Search Modes & Parameters
    4. Date & Time Filtering
    5. Rate Limit Prevention
    6. Batch Mode for Multiple Users
    7. Scraping from Tweet Links
    8. Troubleshooting & Error Handling
    9. Tips for Best Results

    ═══════════════════════════════════════════════════════════════

    1️⃣ GETTING STARTED - FIRST TIME SETUP

    Before your first scrape, you MUST set up cookie authentication:

    Step 1: Install the "cookie-editor" browser extension
    • Chrome: Search "cookie-editor" in Chrome Web Store
    • Firefox: Search "cookie-editor" in Firefox Add-ons
    • Look for the extension by "cgagnier"

    Step 2: Configure your cookies (see section 2 below)

    📹 INSTALLATION VIDEO: https://youtu.be/RKX2sgQVgBg
    Watch this for complete setup walkthrough

    ═══════════════════════════════════════════════════════════════

    2️⃣ COOKIE AUTHENTICATION (REQUIRED)

    WHY: Twitter requires authentication to access tweets. Cookies allow
    the scraper to access Twitter on your behalf.

    HOW TO GET COOKIES:
    1. Log in to Twitter/X.com in your browser
    2. Click the cookie-editor extension icon
    3. Click "Export" button
    4. Click "Copy to Clipboard" (cookies are now copied as JSON)
    5. Return to Chi Tweet Scraper
    6. Click "▶ Show Cookie Input" in the Twitter Cookies section
    7. Paste the JSON into the text box
    8. Click "Save Cookies"
    9. You should see "✓ Cookies saved successfully"

    WHEN TO UPDATE:
    • Cookies expire after 1-2 weeks typically
    • If you see "🔑 Authentication Required" during scraping
    • After changing your Twitter password
    • If you log out of Twitter in your browser

    AUTOMATIC RECOVERY:
    • If cookies expire during scraping, a popup will appear
    • Your progress is automatically saved
    • Follow the same steps to paste new cookies
    • Click "Update & Resume" to continue from where you left off
    • NO DATA IS LOST - scraping resumes seamlessly

    ═══════════════════════════════════════════════════════════════

    3️⃣ SEARCH MODES & PARAMETERS

    🔹 USERNAME MODE (Default)
    • Scrapes all tweets from a specific user
    • Enter username WITHOUT @ symbol (or with, works both ways)
    • Example: "elonmusk" or "@elonmusk"
    • Filters out replies automatically

    🔹 KEYWORDS MODE
    • Searches for tweets containing specific keywords
    • Enter multiple keywords separated by commas
    • Example: "bitcoin, cryptocurrency, blockchain"
    
    OPERATORS:
    • OR (default): Finds tweets with ANY of the keywords
    • AND: Finds tweets with ALL keywords together
    
    Use Cases:
    • OR for broad research: "climate change, global warming"
    • AND for specific topics: "Tesla AND earnings"

    🔹 BATCH MODE
    • Scrape multiple usernames in one operation
    • Perfect for competitive analysis or research
    
    How to Use:
    1. Enable "Batch mode" checkbox
    2. Click "Select File"
    3. Choose a .txt or .csv file with usernames
    4. File format: One username per line, OR comma-separated
    
    Example file content:
    ```
    elonmusk
    BillGates
    sundarpichai
    ```
    OR: `elonmusk, BillGates, sundarpichai`

    ═══════════════════════════════════════════════════════════════

    4️⃣ DATE & TIME FILTERING

    📅 DATE FORMAT: YYYY-MM-DD
    Examples: 2024-01-01, 2024-12-25, 2023-06-15

    🕐 TIME FORMAT (Optional): HH:MM:SS or HH:MM (24-hour)
    Examples: 14:30:00, 09:00, 23:59:59

    HOW IT WORKS:
    • From Date: Start of your date range (inclusive)
    • To Date: End of your date range (inclusive)
    • Times are optional - if left as default:
        * Start time: 00:00:00 (midnight)
        * End time: 23:59:59 (end of day)

    EXAMPLES:
    1. Full day scrape:
        From: 2024-01-01  Time: 00:00:00
        To:   2024-01-31  Time: 23:59:59
        → Scrapes all of January 2024

    2. Specific time window:
        From: 2024-12-25  Time: 09:00:00
        To:   2024-12-25  Time: 17:00:00
        → Only tweets between 9 AM - 5 PM on Christmas

    3. Multi-day precise:
        From: 2024-06-01  Time: 14:00
        To:   2024-06-07  Time: 14:00
        → Exactly one week starting at 2 PM

    ⚠️ IMPORTANT NOTES:
    • Future dates automatically adjusted to current time
    • Wider date ranges may take longer
    • Empty results may indicate no tweets in that period

    ═══════════════════════════════════════════════════════════════

    5️⃣ RATE LIMIT PREVENTION (RECOMMENDED FOR LARGE SCRAPES)

    Twitter limits how many requests you can make. Use breaks to avoid
    hitting these limits.

    HOW TO ENABLE:
    1. Check "Enable random breaks"
    2. Configure settings:
        • Every X tweets: How often to take breaks (default: 100)
        • Break duration: Random between min-max minutes
    
    RECOMMENDED SETTINGS:
    • Small scrapes (<500 tweets): Disabled or Every 200 tweets
    • Medium scrapes (500-2000): Every 150 tweets, 3-7 min
    • Large scrapes (2000+): Every 100 tweets, 5-10 min
    • Very large/overnight: Every 75 tweets, 8-15 min

    WHAT HAPPENS DURING BREAKS:
    • Scraping pauses automatically
    • You'll see: "☕ Taking a X-minute break..."
    • Countdown timer shows time remaining
    • Resumes automatically when break ends
    • Can still click "Stop" if needed

    NOTE: This is DIFFERENT from Twitter's rate limits (which show
    as "⏳ RATE LIMIT HIT! Waiting 15 minutes...")

    ═══════════════════════════════════════════════════════════════

    6️⃣ BATCH MODE FOR MULTIPLE USERS

    Perfect for scraping many accounts at once.

    SETUP:
    1. Create a text file (.txt) with usernames:
    ```
        nasa
        spacex
        elonmusk
    ```
    
    2. Or use CSV format:
    ```
        nasa, spacex, elonmusk
    ```

    3. In the app:
        • Check "Batch mode"
        • Click "Select File"
        • Choose your file
        • Set date range (applies to ALL users)
        • Click "Start"

    PROGRESS TRACKING:
    • See "Processing user 3/10: @username"
    • Each user saved to separate file
    • If interrupted, resume dialog offers to continue

    ERROR HANDLING:
    • If one user fails, others continue
    • Final summary shows: "5/10 users successful"
    • Failed users logged in Activity Log

    ═══════════════════════════════════════════════════════════════

    7️⃣ SCRAPING FROM TWEET LINKS

    Use the "Scrape by Links" tab to get details from specific tweets.

    SUPPORTED FILES:
    • .txt files: One URL per line
    • .xlsx/.xls files: URLs in first column

    URL FORMAT:
    • https://twitter.com/username/status/1234567890
    • https://x.com/username/status/1234567890
    • Both formats work

    HOW TO USE:
    1. Switch to "Scrape by Links" tab
    2. Click "Browse..." and select your file
    3. Choose export format (Excel/CSV)
    4. Click "Start Link Scrape"

    EXAMPLE FILE (.txt):
    ```
    https://twitter.com/nasa/status/1234567890
    https://x.com/spacex/status/9876543210
    https://twitter.com/elonmusk/status/5555555555
    ```

    ═══════════════════════════════════════════════════════════════

    8️⃣ TROUBLESHOOTING & ERROR HANDLING

    🔑 AUTHENTICATION ERRORS
    Problem: "🔑 Authentication Required" popup appears
    
    What This Means:
    • Your Twitter cookies have expired (normal behavior)
    • This happens to everyone - it's not a bug
    
    Solution: 
    1. A popup window will appear automatically (if it doesn't, click "Show Cookie Input" and put new cookies)
    2. Follow the instructions in the popup
    3. Paste new cookies (see Section 2 for how)
    4. Click "Update & Resume"
    5. Scraping continues from exactly where it stopped
    6. Your progress is automatically saved - nothing is lost

    🔌 NETWORK ERRORS
    Problem: "🔌 Network Connection Lost" popup
    
    Causes:
    • Internet disconnected
    • WiFi dropped
    • Router restarted
    • ISP temporary outage
    
    Solution:
    1. Fix your internet connection
    2. The popup will show "Test Connection" button
    3. Click "Test Connection" - it will check if you're back online
    4. When it shows green checkmark, click "Resume"
    5. Scraping continues from last saved point
    6. Your progress is never lost

    Alternative:
    • Click "Cancel Scraping" if you want to stop
    • Your data is saved - you can resume later

    📭 EMPTY PAGES
    Problem: "Hit multiple consecutive empty pages..."
    
    What This Means:
    • No tweets found in several consecutive searches
    • Could be end of date range, or gap in posting
    
    Your Options:
    • Yes: Keep searching (maybe they posted later)
    • No: Stop this user, save what we found
    • Cancel: Stop entire operation

    ⏳ RATE LIMITS (Twitter's Limits)
    Message: "⏳ RATE LIMIT HIT! Waiting 15 minutes..."
    
    What This Is:
    • Twitter's built-in rate limit (not a bug!)
    • Twitter limits how fast you can scrape
    • Happens to all scrapers, including official ones
    
    What Happens:
    • Automatic 15-minute countdown
    • Shows remaining time: "14:23 remaining"
    • Resumes automatically after countdown
    • Your progress is saved throughout
    
    How to Avoid:
    • Enable "Rate Limit Prevention" breaks
    • Scrape smaller date ranges
    • Spread large scrapes over multiple days

    💾 AUTO-SAVE FEATURE
    • Progress saved every 50 tweets automatically
    • Also saved when any error occurs
    • Safe to stop anytime - can resume later
    • State file saved in: data/scraper_state.json

    🔄 RESUME FUNCTIONALITY
    • If app crashes or you close it during scraping
    • Next time you open, you'll see "Resume Previous Session?"
    • Choose "Yes" to continue from exactly where you stopped
    • All your progress is preserved

    ═══════════════════════════════════════════════════════════════

    9️⃣ TIPS FOR BEST RESULTS

    ✅ DO:
    • Update cookies proactively s
    • Start with small date ranges to test (1-7 days)
    • Enable breaks for scrapes over 500 tweets
    • Keep Activity Log visible to monitor progress
    • Use batch mode for multiple users (more efficient)
    • Save your username lists as .txt files for reuse

    ❌ DON'T:
    • Don't scrape massive date ranges at once (split into months)
    • Don't run multiple instances simultaneously
    • Don't close app during "🔑 Authenticating..." phase
    • Don't panic if you see errors - they're handled automatically
    • Don't delete data/scraper_state.json while scraping

    ⚡ OPTIMIZATION:
    • Excel format: Better for viewing/filtering in spreadsheet
    • CSV format: Faster for very large datasets (10,000+ tweets)
    • Keywords + AND: More precise, faster results
    • Keywords + OR: Broader results, takes longer
    • Narrow date ranges: Faster, more reliable

    🎯 USE CASES & EXAMPLES:
    
    Market Research:
    • Keywords: "iPhone 15, Galaxy S24"
    • Operator: OR
    • Date: Last 30 days
    • Result: Public sentiment about competing products
    
    Competitive Analysis:
    • Batch mode: List of competitor Twitter accounts
    • Date: Last quarter
    • Result: Compare posting frequency and engagement
    
    Academic Research:
    • Keywords: "climate change, carbon emissions"
    • Operator: OR
    • Date: Specific event period
    • Enable breaks for large dataset
    
    Brand Monitoring:
    • Username: Your brand's Twitter
    • Date: Last year
    • Result: Archive of all your brand's tweets
    
    Event Analysis:
    • Keywords: Event hashtags
    • Date: Event dates (specific hours)
    • Result: Real-time reactions during event

    ═══════════════════════════════════════════════════════════════

    📹 VIDEO TUTORIALS

    🎬 Installation & Setup (5 min):
    https://youtu.be/RKX2sgQVgBg
    → First-time setup, cookie installation walkthrough

    🎬 How to Use (10 min):
    https://youtu.be/AbdpX6QZLm4
    → Complete tutorial with examples and tips

    ═══════════════════════════════════════════════════════════════

    ❓ FREQUENTLY ASKED QUESTIONS

    Q: How often do I need to update cookies?
    A: Every time it asks. The app will show a popup when they expire.

    Q: Can I scrape while on breaks or rate limits?
    A: Yes! The app handles everything automatically. Just leave it running.

    Q: What if I close the app accidentally?
    A: No problem! Reopen it and you'll see "Resume Previous Session?"

    Q: Can I scrape private accounts?
    A: Only if you follow them and are logged into that account.

    Q: How many tweets can I scrape?
    A: No hard limit, but larger scrapes take longer. Use date ranges wisely.

    Q: Can I use this for commercial purposes?
    A: Check Twitter's Terms of Service for data usage policies.

    Q: Why does it say "Empty pages"?
    A: Either no tweets in that date range, or Twitter API limitations.

    ═══════════════════════════════════════════════════════════════

    🆘 STILL NEED HELP?

    1. Check the Activity Log for specific error messages
    2. Watch the video tutorials (links above)
    3. Try a simple test scrape first:
    • Mode: Username
    • User: "twitter"
    • Date: Last 7 days
    • If this works, your setup is correct!

    4. Common fixes:
    • Error during scraping? → Check your internet
    • Authentication error? → Update cookies
    • Empty results? → Try different date range

    ═══════════════════════════════════════════════════════════════

    Made with ❤️ by Chi | Version 2.0 | Last Updated: December 2025

    Remember: Errors are handled automatically. The app saves your progress
    constantly. You can always resume. Happy scraping! 🚀
    """

        guide_window = tk.Toplevel(self.root)
        guide_window.title("Chi Tweet Scraper - Complete User Guide")
        guide_window.geometry("900x700")
        guide_window.resizable(True, True)
        guide_window.transient(self.root)
        guide_window.grab_set()

        # Center window
        guide_window.update_idletasks()
        x = (guide_window.winfo_screenwidth() // 2) - 450
        y = (guide_window.winfo_screenheight() // 2) - 350
        guide_window.geometry(f"900x700+{x}+{y}")

        # Main container
        main_container = ttk.Frame(guide_window, padding="15")
        main_container.pack(fill="both", expand=True)

        # Title
        title_label = ttk.Label(
            main_container,
            text="📖 Complete User Guide",
            font=("Segoe UI", 16, "bold"),
        )
        title_label.pack(pady=(0, 10))

        # Text widget with scrollbar
        text_frame = ttk.Frame(main_container)
        text_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        text_widget = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            yscrollcommand=scrollbar.set,
            padx=15,
            pady=10,
        )
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=text_widget.yview)

        # Insert text
        text_widget.insert("1.0", guide_text)

        # Make hyperlinks clickable
        def add_hyperlink(url, start, end):
            text_widget.tag_add(url, start, end)
            text_widget.tag_config(url, foreground="#0066cc", underline=1)
            text_widget.tag_bind(url, "<Button-1>", lambda e: webbrowser.open(url))
            text_widget.tag_bind(
                url, "<Enter>", lambda e: text_widget.config(cursor="hand2")
            )
            text_widget.tag_bind(
                url, "<Leave>", lambda e: text_widget.config(cursor="")
            )

        # Find and link YouTube URLs
        for url in ["https://youtu.be/RKX2sgQVgBg", "https://youtu.be/AbdpX6QZLm4"]:
            start_idx = "1.0"
            while True:
                start_idx = text_widget.search(url, start_idx, tk.END)
                if not start_idx:
                    break
                end_idx = f"{start_idx}+{len(url)}c"
                add_hyperlink(url, start_idx, end_idx)
                start_idx = end_idx

        text_widget.config(state="disabled")

        # Bottom buttons
        button_frame = ttk.Frame(main_container)
        button_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(
            button_frame,
            text="📹 Watch Setup Video",
            command=lambda: webbrowser.open("https://youtu.be/RKX2sgQVgBg"),
        ).pack(side="left", padx=(0, 5))

        ttk.Button(
            button_frame,
            text="📹 Watch Tutorial Video",
            command=lambda: webbrowser.open("https://youtu.be/AbdpX6QZLm4"),
        ).pack(side="left")

        ttk.Button(button_frame, text="Close", command=guide_window.destroy).pack(
            side="right"
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
