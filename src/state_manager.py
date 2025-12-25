import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "scraper_state.json")


class StateManager:
    """Manages scraping session state for resumable operations."""

    def __init__(self):
        self.state_dir = os.path.dirname(STATE_FILE)
        os.makedirs(self.state_dir, exist_ok=True)

    def save_state(self, state_data: Dict[str, Any]) -> bool:
        """
        Save current scraping state to file.

        Args:
            state_data: Dictionary containing:
                - mode: 'single' or 'batch' or 'links'
                - current_index: Current position in batch
                - usernames: List of usernames (batch mode)
                - current_username: Current username being scraped
                - last_tweet_id: Last successfully scraped tweet ID
                - tweets_scraped: Total tweets scraped so far
                - settings: Export format, dates, keywords, etc.
                - timestamp: When state was saved
                - file_path: Path to batch file (if batch mode)
                - links_file_path: Path to links file (if links mode)
                - output_path: Current output file path
        """
        try:
            state_data["timestamp"] = datetime.now().isoformat()

            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)

            logger.info(f"State saved successfully: {state_data.get('mode')} mode")
            return True

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Load saved state from file.

        Returns:
            State dictionary or None if no state exists
        """
        if not os.path.exists(STATE_FILE):
            return None

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            logger.info(f"State loaded: {state.get('mode')} mode")
            return state

        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def clear_state(self) -> bool:
        """Delete the state file."""
        try:
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
                logger.info("State file cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear state: {e}")
            return False

    def has_saved_state(self) -> bool:
        """Check if a saved state exists."""
        return os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) > 0

    def get_state_summary(self) -> Optional[str]:
        """
        Get a human-readable summary of the saved state.

        Returns:
            Summary string or None if no state exists
        """
        state = self.load_state()
        if not state:
            return None

        mode = state.get("mode", "unknown")
        tweets = state.get("tweets_scraped", 0)
        timestamp = state.get("timestamp", "")

        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = "Unknown time"

        if mode == "batch":
            current_idx = state.get("current_index", 0)
            total_users = len(state.get("usernames", []))
            current_user = state.get("current_username", "Unknown")

            return (
                f"Mode: Batch scraping\n"
                f"Progress: User {current_idx + 1}/{total_users} (@{current_user})\n"
                f"Tweets scraped: {tweets}\n"
                f"Last saved: {time_str}"
            )

        elif mode == "single":
            username = state.get("current_username", "Unknown")
            return (
                f"Mode: Single user scraping\n"
                f"Username: @{username}\n"
                f"Tweets scraped: {tweets}\n"
                f"Last saved: {time_str}"
            )

        elif mode == "links":
            current_idx = state.get("current_index", 0)
            total_links = state.get("total_links", 0)

            return (
                f"Mode: Link scraping\n"
                f"Progress: {current_idx}/{total_links} links\n"
                f"Tweets scraped: {tweets}\n"
                f"Last saved: {time_str}"
            )

        return f"Mode: {mode}\nTweets: {tweets}\nLast saved: {time_str}"
