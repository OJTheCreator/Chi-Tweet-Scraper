import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from tkinter.scrolledtext import ScrolledText
import threading
import asyncio
from datetime import datetime
import os
import sys
from PIL import Image, ImageTk, ImageDraw

# --- Your existing imports ---
from create_cookie import convert_editthiscookie_to_twikit_format
from scraper import scrape_tweets


# Utility for PyInstaller resource path
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)


class TweetScraperApp:
    def __init__(self, root):
        self.root = root
        root.title("Chi Tweet Scraper")
        root.geometry("700x900")

        self.task = None
        self.loop = None
        self.file_path = None

        # Logo (circular)
        try:
            logo_file = resource_path(os.path.join("..", "assets", "logo.png"))
            img = (
                Image.open(logo_file).convert("RGBA").resize((80, 80), Image.ANTIALIAS)
            )
            mask = Image.new("L", (80, 80), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 80, 80), fill=255)
            img.putalpha(mask)
            self.logo_img = ImageTk.PhotoImage(img)
            tk.Label(root, image=self.logo_img).grid(
                row=0, column=0, columnspan=3, pady=10
            )
        except Exception:
            pass  # Logo is optional

        # Export format
        tk.Label(root, text="Export Format:").grid(row=1, column=0, sticky="w", padx=10)
        self.format_var = tk.StringVar(value="Excel")
        ttk.Combobox(
            root,
            textvariable=self.format_var,
            values=["Excel", "CSV"],
            state="readonly",
            width=30,
        ).grid(row=1, column=1, columnspan=2, pady=5, sticky="w")

        # Batch mode toggle
        self.batch_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            root,
            text="Batch mode (usernames from file)",
            variable=self.batch_var,
            command=self.toggle_batch,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=10)
        self.file_btn = tk.Button(
            root,
            text="Select Username File…",
            command=self.select_file,
            state="disabled",
        )
        self.file_btn.grid(row=3, column=0, columnspan=3, sticky="w", padx=20, pady=2)

        # Search mode (disabled in batch)
        tk.Label(root, text="Search by:").grid(row=4, column=0, sticky="w", padx=10)
        self.mode_var = tk.StringVar(value="Username")
        self.mode_menu = ttk.Combobox(
            root,
            textvariable=self.mode_var,
            values=["Username", "Keywords"],
            state="readonly",
            width=30,
        )
        self.mode_menu.grid(row=4, column=1, pady=5, columnspan=2, sticky="w")
        self.mode_menu.bind("<<ComboboxSelected>>", self.update_mode)

        # Username entry
        self.username_label = tk.Label(root, text="Username:")
        self.username_label.grid(row=5, column=0, sticky="w", padx=10)
        self.username_entry = tk.Entry(root, width=30)
        self.username_entry.grid(row=5, column=1, columnspan=2, pady=5, sticky="w")

        # Keywords + operator
        self.keyword_label = tk.Label(root, text="Keywords (comma-separated):")
        self.keyword_entry = tk.Entry(root, width=30)
        tk.Label(root, text="Operator:").grid(row=7, column=0, sticky="w", padx=10)
        self.op_var = tk.StringVar(value="OR")
        self.op_menu = ttk.Combobox(
            root,
            textvariable=self.op_var,
            values=["OR", "AND"],
            state="readonly",
            width=30,
        )
        self.op_menu.grid(row=7, column=1, columnspan=2, pady=5, sticky="w")

        # Date range
        tk.Label(root, text="Start Date (YYYY-MM-DD):").grid(
            row=8, column=0, sticky="w", padx=10
        )
        self.start_entry = tk.Entry(root, width=30)
        self.start_entry.grid(row=8, column=1, pady=5, sticky="w")
        tk.Label(root, text="End Date (YYYY-MM-DD):").grid(
            row=9, column=0, sticky="w", padx=10
        )
        self.end_entry = tk.Entry(root, width=30)
        self.end_entry.grid(row=9, column=1, pady=5, sticky="w")

        # Cookie JSON
        tk.Label(root, text="Paste Cookie JSON:").grid(
            row=10, column=0, sticky="nw", padx=10
        )
        self.cookie_text = tk.Text(root, width=45, height=5)
        self.cookie_text.grid(row=10, column=1, columnspan=2, pady=5)

        # Progress bar
        self.progress = ttk.Progressbar(root, length=400, mode="indeterminate")
        self.progress.grid(row=11, column=0, columnspan=3, pady=5)
        self.progress.grid_remove()

        # Buttons
        tk.Button(root, text="Save Cookies", command=self.save_cookies).grid(
            row=12, column=2, sticky="e", padx=10
        )
        self.scrape_button = tk.Button(
            root, text="Start Scraping", command=self.start_scrape_thread
        )
        self.scrape_button.grid(row=13, column=2, sticky="e", pady=5, padx=10)

        self.stop_btn = tk.Button(
            root, text="Stop Scraping", command=self.stop_scrape, state="disabled"
        )
        self.stop_btn.grid(row=13, column=0, sticky="w", padx=10)
        tk.Button(root, text="Clear Logs", command=self.clear_logs).grid(
            row=14, column=2, sticky="e", padx=10, pady=5
        )
        tk.Button(root, text="Cookie Guide", command=self.show_guide).grid(
            row=14, column=0, sticky="w", padx=10
        )

        # Status label
        self.count_lbl = tk.Label(root, text="Tweets scraped: 0")
        self.count_lbl.grid(row=15, column=2, sticky="e", padx=10)

        # Logs + live preview
        tk.Label(root, text="Logs / Live Preview:").grid(
            row=16, column=0, sticky="w", padx=10
        )
        self.log_text = ScrolledText(root, width=80, height=12, bg="#f7f7f7")
        self.log_text.grid(row=17, column=0, columnspan=3, padx=10, pady=5)

        self.update_mode()

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
            self.log(f"Loaded usernames from: {path}")

    def update_mode(self, *_):
        if self.mode_var.get() == "Username":
            self.username_label.grid()
            self.username_entry.grid()
            self.keyword_label.grid_remove()
            self.keyword_entry.grid_remove()
            self.op_menu.state(["disabled"])
        else:
            self.username_label.grid_remove()
            self.username_entry.grid_remove()
            self.keyword_label.grid(row=6, column=0, sticky="w", padx=10)
            self.keyword_entry.grid(row=6, column=1, columnspan=2, pady=5, sticky="w")
            self.op_menu.state(["!disabled"])

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"{timestamp} – {msg}\n")
        self.log_text.see(tk.END)

    def clear_logs(self):
        self.log_text.delete("1.0", tk.END)

    def save_cookies(self):
        raw = self.cookie_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("No Cookies", "Paste cookie JSON first.")
            return
        if convert_editthiscookie_to_twikit_format(raw):
            self.log("Cookies saved successfully.")
        else:
            self.log("Failed to save cookies (invalid JSON).")

    def start_scrape_thread(self):
        fmt = self.format_var.get().lower()
        start, end = self.start_entry.get().strip(), self.end_entry.get().strip()
        # Date validation
        try:
            datetime.strptime(start, "%Y-%m-%d")
            datetime.strptime(end, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid Date", "Use YYYY-MM-DD format.")
            return

        # Decide mode
        if self.batch_var.get():
            if not self.file_path:
                messagebox.showwarning("No File", "Select a username file.")
                return
            with open(self.file_path, encoding="utf-8") as f:
                txt = f.read().replace("\n", ",")
            users = [u.strip() for u in txt.split(",") if u.strip()]
            if not users:
                messagebox.showwarning("Empty", "No usernames found in file.")
                return
            target = ("batch", users)
        else:
            mode = self.mode_var.get()
            user = self.username_entry.get().strip() if mode == "Username" else None
            kws = (
                [k.strip() for k in self.keyword_entry.get().split(",")]
                if mode == "Keywords"
                else None
            )
            if (mode == "Username" and not user) or (mode == "Keywords" and not kws):
                messagebox.showwarning("Missing", "Fill username or keywords.")
                return
            target = ("single", user, kws)

        # Prepare UI
        self.scrape_button.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.grid()
        self.progress.start(50)
        self.count_lbl.config(text="Tweets scraped: 0")
        self.clear_logs()
        self.log("Starting scrape...")

        # Launch thread
        threading.Thread(
            target=self._run_scrape, args=(target, start, end, fmt), daemon=True
        ).start()

    def _run_scrape(self, target, start, end, fmt):
        def progress_cb(x):
            if isinstance(x, int):
                self.count_lbl.config(text=f"Tweets scraped: {x}")
            else:
                self.log(str(x))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if target[0] == "batch":
            # batch: loop users
            async def batch_task():
                for u in target[1]:
                    progress_cb(f"🔄 Scraping {u}...")
                    out, cnt = await scrape_tweets(
                        username=u,
                        start_date=start,
                        end_date=end,
                        keywords=None,
                        use_and=False,
                        export_format=fmt,
                        progress_callback=progress_cb,
                        should_stop_callback=lambda: self.task.done(),
                    )
                    progress_cb(f"✅ {cnt} tweets saved for {u} → {out}")
                return [], 0

            self.task = loop.create_task(batch_task())
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
                )
            )

        try:
            output, total = loop.run_until_complete(self.task)
            if target[0] == "single":
                progress_cb(f"✅ Done: {total} tweets → {output}")
                messagebox.showinfo("Done", f"✅ {total} tweets saved to:\n{output}")
            else:
                messagebox.showinfo("Done", "Batch scraping complete.")
        except asyncio.CancelledError:
            self.log("Scrape cancelled by user.")
        except Exception as e:
            self.log(f"Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.progress.stop()
            self.progress.grid_remove()
            self.scrape_button.config(state="normal")
            self.stop_btn.config(state="disabled")

    def stop_scrape(self):
        if self.task and not self.task.done():
            self.task.cancel()
            self.log("Stop requested.")

    def show_guide(self):
        messagebox.showinfo(
            "How to Get Cookies",
            "1. Export JSON from EditThisCookie\n"
            "2. Paste JSON into the cookie box and click Save Cookies\n"
            "3. Choose export format, mode, and dates\n"
            "4. Click Start Scraping\n"
            "5. Use Stop to cancel and Clear Logs to reset logs",
        )


if __name__ == "__main__":
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "cookies"), exist_ok=True)
    os.makedirs(
        os.path.join(os.path.dirname(__file__), "..", "data", "exports"), exist_ok=True
    )

    root = tk.Tk()  # <— Make sure to instantiate the Tk() root here
    app = TweetScraperApp(root)
    root.mainloop()
