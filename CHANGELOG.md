# Changelog

All notable changes to Chi Tweet Scraper will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2025-01-02

### 🎉 New Features

#### Search & Filtering
- **Keyword Search Mode** — Search tweets by keywords instead of just usernames
  - Support for multiple keywords (comma-separated)
  - AND/OR operators for flexible searching
- **Time Filtering** — Filter tweets by specific hours, not just dates
  - Format: HH:MM:SS (24-hour)
  - Defaults to full day (00:00:00 - 23:59:59) if not specified

#### Batch Processing
- **Batch Mode** — Scrape multiple usernames in a single session
  - Load usernames from .txt file (one per line or comma-separated)
  - Each user's tweets saved to separate export files
  - Progress tracked across all users

#### Link Scraping
- **New "Scrape by Links" Tab** — Extract data from specific tweet URLs
  - Support for .txt files (one URL per line)
  - Support for .xlsx files (URLs in first column)
  - Works with both twitter.com and x.com URLs

#### Rate Limit Prevention
- **Configurable Breaks** — Automatic pauses during large scrapes
  - Set tweet interval (e.g., every 100 tweets)
  - Random pause duration (e.g., 5-10 minutes)
  - Helps avoid Twitter rate limits

#### Session Management
- **Auto-Resume** — Never lose progress on interrupted scrapes
  - State saved automatically every 25 tweets
  - Resume prompt when reopening the app
  - Works for single, batch, and link scraping modes

### 🎨 UI Improvements

#### Layout & Design
- **Compact Interface** — Better fit on smaller screens
  - Default size: 680×620 (reduced from 720×780)
  - Minimum size: 640×560
  - Reduced padding and margins throughout
- **Tabbed Interface** — Clean separation of features
  - "Main" tab for username/keyword scraping
  - "Scrape by Links" tab for URL-based scraping
- **Collapsible Cookie Section** — Hidden by default, click to expand
- **Modern Blue Theme** — Clean, professional appearance

#### Activity Log
- **Always Visible** — Log section expands with window
- **Clear Button** — Quick log clearing
- **Real-time Updates** — Live progress during scraping
- **Timestamps** — Each log entry shows time

#### Progress Indication
- **Live Tweet Counter** — Shows "Scraped: X" during operation
- **Progress Bar** — Visual indication of activity
- **Status Messages** — Clear feedback on current operation

### 🛡️ Error Handling

#### Interactive Recovery Dialogs
- **Cookie Expiry Dialog**
  - Shows progress saved so far
  - Paste new cookies directly in dialog
  - Validates cookies before resuming
- **Network Error Dialog**
  - "Test Connection" button to verify connectivity
  - Resume only enabled after successful test
  - Option to stop and save current progress
- **Unknown Error Dialog**
  - Displays error message
  - Retry or stop options

#### Automatic Retry Logic
- Progressive backoff for transient errors
- Up to 5 retries before showing dialog
- Network errors: 10s → 30s → 1min → 5min → 15min delays

### 🔧 Technical Improvements

#### Code Architecture
- **State Manager** — Centralized session persistence
- **Resource Path Helper** — Proper asset loading for PyInstaller builds
- **Async Scraping** — Non-blocking UI during operations
- **Thread Safety** — Proper threading for background tasks

#### Cookie Handling
- **Cookie-Editor Format Support** — Direct paste from browser extension
- **Automatic Format Conversion** — Converts to Twikit format
- **Duplicate Removal** — Cleans duplicate cookies automatically

#### Export
- **Consistent Output** — Same columns for all export types
- **UTF-8 Encoding** — Proper handling of international characters
- **Auto-created Directories** — Creates export folder if missing

### 📖 Documentation

- **Comprehensive Help Guide** — In-app documentation
  - Quick start instructions
  - Cookie setup guide
  - Feature explanations
  - Pro tips for large scrapes
- **YouTube Tutorial Links** — Quick access to video guides
- **Updated README** — Complete feature documentation

### 🐛 Bug Fixes

- Fixed progress bar covering activity log
- Fixed cookie section not collapsing properly
- Fixed date validation for edge cases
- Fixed export path handling on different OS
- Fixed window icon not showing on some systems

### ⚠️ Breaking Changes

- Main entry point changed from `src/gui.py` to `GUI.py`
- Minimum window size increased to 640×560

---

## [1.0.0] - 2024-12-XX

### Initial Release

- Basic tweet scraping by username
- Date range filtering
- Cookie-based authentication
- Excel export (.xlsx)
- Simple GUI interface
- Cookie expiration detection

---

## Upgrade Guide

### From v1.0.0 to v1.1.0

1. **Backup your cookies** — Export from the old version if needed
2. **Replace files** — Copy new `GUI.py` and `src/` folder
3. **Update dependencies** — Run `pip install -r requirements.txt`
4. **Launch** — Run `python GUI.py`

Your existing cookie file in `/cookies` will continue to work.

---

## Future Roadmap

- [ ] Dark mode theme
- [ ] Proxy support
- [ ] Advanced filtering (retweets, replies, media)
- [ ] Scheduled scraping
- [ ] Database export option
- [ ] Multi-language support

---

<p align="center">Made with ❤️ by OJ</p>
