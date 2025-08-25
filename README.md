## 🐦 Chi Tweet Scraper

<p align="center"> <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python" /> <img src="https://img.shields.io/badge/Tkinter-GUI-orange?style=for-the-badge" /> <img src="https://img.shields.io/badge/Twikit-Scraper-green?style=for-the-badge" /> <img src="https://img.shields.io/badge/Export-Excel-success?style=for-the-badge&logo=microsoft-excel" /> </p>

Chi Tweet Scraper is a desktop app built with **Python**, **Tkinter**, and **Twikit** that lets you scrape tweets for any username within a chosen date range. It uses a cookie-based login system (via **EditThisCookie**) to stay authenticated, and exports all results into **.xlsx** or **.CSV** files for easy analysis.

---

### ✨ Features

✅ **Simple GUI** – Enter username and a date range directly in the app.
✅ **Secure Login** – Paste cookies from your browser; no passwords are ever stored.
✅ **Export Ready** – Tweets are saved as Excel files in the `/data/exports` directory.
✅ **Multi-User Support** – Scrape tweets from multiple usernames in a single session.
✅ **Cookie Expiration Detection** – The app prompts you to refresh your cookies when they expire.
✅ **Portable Build** – Can be used as `.exe` file for Windows users.

---

### 📸 Screenshots
![alt text](<Screenshot 2025-08-25 183747.png>)

---

###  Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/Ojthecreator/Tweet_Scraper_app.git](https://github.com/YOUR_USERNAME/Tweet_Scraper_app.git)
    cd Tweet_Scraper_app
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # For Windows
    python -m venv .venv
    .venv\Scripts\activate

    # For Linux/Mac
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

---

### Usage

1.  **Launch the GUI:**
    ```bash
    python -m src.gui
    ```

2.  **Paste your Twitter cookies** (copied from the **Cookie Editor** browser extension after logging in a twitter account on your browser).

3.  **Enter the Twitter username** and the **desired date range** in the provided fields.

4.  **Click "Scrape"** 

---

###  Build as Executable

To create a portable `.exe` file for Windows:

```bash
pyinstaller --noconfirm --onefile --windowed src/gui.py