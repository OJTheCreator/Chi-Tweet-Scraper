import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "scraper_state.json")


class StateManager:
    """Manages scraping session state for resumable operations."""

    def __init__(self, state_file: str = None):
        """
        Initialize StateManager.

        Args:
            state_file: Optional custom path for state file (useful for testing)
        """
        self.state_file = state_file or STATE_FILE
        self.state_dir = os.path.dirname(self.state_file)
        os.makedirs(self.state_dir, exist_ok=True)

    def save_state(self, state_data: Dict[str, Any]) -> bool:
        """
        Save current scraping state to file.

        Args:
            state_data: Dictionary containing:
                - mode: 'single' or 'batch' or 'links'
                - current_index: Current position in batch/links
                - usernames: List of usernames (batch mode)
                - current_username: Current username being scraped
                - last_tweet_id: Last successfully scraped tweet ID
                - tweets_scraped: Total tweets scraped so far
                - settings: Export format, dates, keywords, etc.
                - file_path: Path to batch file (if batch mode)
                - links_file_path: Path to links file (if links mode)
                - output_path: Current output file path
                - seen_tweet_ids: Set/list of already scraped tweet IDs
                - processed_links: Set/list of already processed links
                - keywords: List of keywords (if keyword mode)

        Returns:
            True if save successful, False otherwise
        """
        try:
            # Add metadata
            state_data["timestamp"] = datetime.now().isoformat()
            state_data["version"] = "2.0"  # For future compatibility

            # Convert sets to lists for JSON serialization
            if "seen_tweet_ids" in state_data and isinstance(
                state_data["seen_tweet_ids"], set
            ):
                state_data["seen_tweet_ids"] = list(state_data["seen_tweet_ids"])

            if "processed_links" in state_data and isinstance(
                state_data["processed_links"], set
            ):
                state_data["processed_links"] = list(state_data["processed_links"])

            # Validate critical fields
            if "mode" not in state_data:
                logger.error("Cannot save state: 'mode' field is required")
                return False

            # Create backup of existing state before overwriting
            if os.path.exists(self.state_file):
                backup_file = self.state_file + ".backup"
                try:
                    with open(self.state_file, "r", encoding="utf-8") as f:
                        backup_data = f.read()
                    with open(backup_file, "w", encoding="utf-8") as f:
                        f.write(backup_data)
                except Exception as e:
                    logger.warning(f"Failed to create state backup: {e}")

            # Write new state
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)

            logger.info(
                f"State saved successfully: {state_data.get('mode')} mode, "
                f"{state_data.get('tweets_scraped', 0)} tweets"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Try to restore from backup if save failed
            backup_file = self.state_file + ".backup"
            if os.path.exists(backup_file):
                try:
                    with open(backup_file, "r", encoding="utf-8") as f:
                        backup_data = f.read()
                    with open(self.state_file, "w", encoding="utf-8") as f:
                        f.write(backup_data)
                    logger.info("Restored state from backup after save failure")
                except:
                    pass
            return False

    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Load saved state from file.

        Returns:
            State dictionary or None if no state exists or is corrupted
        """
        if not os.path.exists(self.state_file):
            return None

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Validate state structure
            if not isinstance(state, dict):
                logger.error("Invalid state: not a dictionary")
                return None

            if "mode" not in state:
                logger.error("Invalid state: missing 'mode' field")
                return None

            # Validate mode-specific fields
            mode = state.get("mode")

            if mode == "batch":
                if "usernames" not in state or not isinstance(state["usernames"], list):
                    logger.error("Invalid batch state: missing or invalid 'usernames'")
                    return None

            elif mode == "single":
                if "current_username" not in state and "keywords" not in state:
                    logger.error("Invalid single state: missing username and keywords")
                    return None

            elif mode == "links":
                if "links_file_path" not in state:
                    logger.error("Invalid links state: missing 'links_file_path'")
                    return None

            logger.info(
                f"State loaded: {mode} mode, "
                f"{state.get('tweets_scraped', 0)} tweets scraped"
            )
            return state

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse state file (corrupted JSON): {e}")
            # Try to load backup
            backup_file = self.state_file + ".backup"
            if os.path.exists(backup_file):
                try:
                    with open(backup_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    logger.info("Loaded state from backup after corruption")
                    return state
                except:
                    pass
            return None

        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def clear_state(self) -> bool:
        """
        Delete the state file and its backup.

        Returns:
            True if cleared successfully, False otherwise
        """
        try:
            files_to_remove = [self.state_file, self.state_file + ".backup"]

            for file_path in files_to_remove:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Removed {os.path.basename(file_path)}")

            logger.info("State files cleared successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to clear state: {e}")
            return False

    def has_saved_state(self) -> bool:
        """
        Check if a valid saved state exists.

        Returns:
            True if state file exists and is not empty
        """
        if not os.path.exists(self.state_file):
            return False

        try:
            return os.path.getsize(self.state_file) > 0
        except:
            return False

    def get_state_summary(self) -> Optional[str]:
        """
        Get a human-readable summary of the saved state.

        Returns:
            Multi-line summary string or None if no state exists
        """
        state = self.load_state()
        if not state:
            return None

        mode = state.get("mode", "unknown")
        tweets = state.get("tweets_scraped", 0)
        timestamp = state.get("timestamp", "")

        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = "Unknown time"

        # Mode-specific summaries
        if mode == "batch":
            current_idx = state.get("current_index", 0)
            usernames = state.get("usernames", [])
            total_users = len(usernames)
            current_user = state.get("current_username", "Unknown")

            # Calculate remaining users
            remaining = total_users - current_idx

            # Get settings info
            settings = state.get("settings", {})
            start_date = settings.get("start_date", "N/A")
            end_date = settings.get("end_date", "N/A")

            return (
                f"📦 Batch Scraping Session\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Current: @{current_user}\n"
                f"Progress: {current_idx}/{total_users} users completed\n"
                f"Remaining: {remaining} users\n"
                f"Tweets collected: {tweets:,}\n"
                f"Date range: {start_date} to {end_date}\n"
                f"Last saved: {time_str}"
            )

        elif mode == "single":
            username = state.get("current_username")
            keywords = state.get("keywords", [])

            # Determine search type
            if username:
                search_info = f"Username: @{username}"
            elif keywords:
                search_info = f"Keywords: {', '.join(keywords)}"
            else:
                search_info = "Unknown search"

            # Get settings info
            settings = state.get("settings", {})
            start_date = settings.get("start_date", "N/A")
            end_date = settings.get("end_date", "N/A")

            return (
                f"👤 Single User/Keyword Scraping\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{search_info}\n"
                f"Tweets collected: {tweets:,}\n"
                f"Date range: {start_date} to {end_date}\n"
                f"Last saved: {time_str}"
            )

        elif mode == "links":
            current_idx = state.get("current_index", 0)
            processed_links = state.get("processed_links", [])
            total_processed = len(processed_links)
            failed_count = state.get("failed_count", 0)

            # Calculate success rate
            if total_processed > 0:
                success_rate = (
                    ((tweets / total_processed) * 100) if total_processed > 0 else 0
                )
            else:
                success_rate = 0

            return (
                f"🔗 Link Scraping Session\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Links processed: {total_processed:,}\n"
                f"Tweets collected: {tweets:,}\n"
                f"Failed/Skipped: {failed_count}\n"
                f"Success rate: {success_rate:.1f}%\n"
                f"Last saved: {time_str}"
            )

        # Fallback for unknown modes
        return (
            f"📊 Scraping Session\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Mode: {mode}\n"
            f"Tweets: {tweets:,}\n"
            f"Last saved: {time_str}"
        )

    def update_progress(
        self,
        tweets_scraped: int = None,
        current_index: int = None,
        current_username: str = None,
        **kwargs,
    ) -> bool:
        """
        Update specific fields in existing state without rewriting everything.
        Useful for frequent progress updates.

        Args:
            tweets_scraped: Updated tweet count
            current_index: Updated index position
            current_username: Updated current username
            **kwargs: Any other fields to update

        Returns:
            True if update successful, False otherwise
        """
        state = self.load_state()
        if not state:
            logger.warning("Cannot update progress: no existing state")
            return False

        try:
            # Update provided fields
            if tweets_scraped is not None:
                state["tweets_scraped"] = tweets_scraped

            if current_index is not None:
                state["current_index"] = current_index

            if current_username is not None:
                state["current_username"] = current_username

            # Update any additional fields
            for key, value in kwargs.items():
                state[key] = value

            # Save updated state
            return self.save_state(state)

        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            return False

    def validate_state_integrity(self) -> tuple[bool, Optional[str]]:
        """
        Validate that saved state is complete and consistent.

        Returns:
            Tuple of (is_valid, error_message)
        """
        state = self.load_state()
        if not state:
            return False, "No saved state found"

        mode = state.get("mode")

        # Check mode-specific requirements
        if mode == "batch":
            if not state.get("usernames"):
                return False, "Batch mode missing usernames list"
            if state.get("current_index", 0) >= len(state.get("usernames", [])):
                return False, "Batch already completed (index out of range)"

        elif mode == "single":
            if not state.get("current_username") and not state.get("keywords"):
                return False, "Single mode missing both username and keywords"

        elif mode == "links":
            links_file = state.get("links_file_path")
            if not links_file:
                return False, "Links mode missing file path"
            if not os.path.exists(links_file):
                return False, f"Links file not found: {links_file}"

        else:
            return False, f"Unknown mode: {mode}"

        # Check if output file exists
        output_path = state.get("output_path")
        if output_path and not os.path.exists(output_path):
            return False, f"Output file not found: {output_path}"

        return True, None

    def get_resume_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information needed specifically for resuming a scrape.

        Returns:
            Dictionary with resume-specific info or None
        """
        state = self.load_state()
        if not state:
            return None

        mode = state.get("mode")

        if mode == "batch":
            current_idx = state.get("current_index", 0)
            all_usernames = state.get("usernames", [])
            remaining_usernames = all_usernames[current_idx:]

            return {
                "mode": "batch",
                "remaining_usernames": remaining_usernames,
                "completed_count": current_idx,
                "total_count": len(all_usernames),
                "tweets_so_far": state.get("tweets_scraped", 0),
                "settings": state.get("settings", {}),
                "state": state,
            }

        elif mode == "single":
            return {
                "mode": "single",
                "username": state.get("current_username"),
                "keywords": state.get("keywords"),
                "tweets_so_far": state.get("tweets_scraped", 0),
                "settings": state.get("settings", {}),
                "state": state,
            }

        elif mode == "links":
            return {
                "mode": "links",
                "links_file": state.get("links_file_path"),
                "current_index": state.get("current_index", 0),
                "tweets_so_far": state.get("tweets_scraped", 0),
                "processed_links": set(state.get("processed_links", [])),
                "settings": state.get("settings", {}),
                "state": state,
            }

        return None


# Utility function for backwards compatibility
def get_state_manager() -> StateManager:
    """Get a singleton StateManager instance."""
    if not hasattr(get_state_manager, "_instance"):
        get_state_manager._instance = StateManager()
    return get_state_manager._instance
