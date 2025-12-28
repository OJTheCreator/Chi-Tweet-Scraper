import os
import json
import asyncio
import csv
import random
from datetime import datetime, timezone
from twikit import Client, TooManyRequests
from openpyxl import Workbook, load_workbook
import logging
import pandas as pd
import re
from collections import defaultdict

TWEET_ID_PATTERN = re.compile(
    r"^https?://(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/(\d+)"
)
RATE_LIMIT_DELAY = 2  # seconds between requests
MAX_NETWORK_RETRIES = 5
RETRY_DELAYS = [30, 60, 120, 300, 600]  # Progressive delays in seconds
MAX_PAGINATION_RETRIES = 3  # Retry pagination errors
MAX_CONSECUTIVE_EMPTY_PAGES = 10  # Allow more empty pages for large date ranges
EMPTY_PAGE_PROMPT_THRESHOLD = 5  # Ask user after 5 empty pages

# Default Paths (overridden by GUI if user picks custom folder)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COOKIES_FILE = os.path.join(BASE_DIR, "cookies", "twikit_cookies.json")
DEFAULT_EXPORT_DIR = os.path.join(BASE_DIR, "data", "exports")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TwitterScraperError(Exception):
    """Custom exception for scraper-specific errors."""

    pass


class CookieExpiredError(TwitterScraperError):
    """Raised when authentication cookies have expired."""

    pass


class NetworkError(TwitterScraperError):
    """Raised when network connection fails."""

    pass


class EmptyPagePromptException(TwitterScraperError):
    """Raised when user input is needed for empty pages."""

    pass


async def authenticate(retry_callback=None, should_stop_callback=None):
    """Authenticate Twikit client using stored cookies with retry logic."""

    for attempt in range(MAX_NETWORK_RETRIES):
        # Check if we should stop
        if should_stop_callback and should_stop_callback():
            raise asyncio.CancelledError("Authentication stopped by user")

        try:
            client = Client(language="en-US")

            if not os.path.exists(COOKIES_FILE):
                raise CookieExpiredError(
                    f"Cookie file not found at {COOKIES_FILE}. Please save cookies first."
                )

            client.load_cookies(COOKIES_FILE)

            # Test authentication
            if should_stop_callback and should_stop_callback():
                raise asyncio.CancelledError("Authentication stopped by user")

            test_result = await client.search_tweet("(from:twitter)", product="Latest")
            logger.info("Authentication successful")
            return client

        except asyncio.CancelledError:
            raise

        except Exception as e:
            if should_stop_callback and should_stop_callback():
                raise asyncio.CancelledError("Authentication stopped by user")

            error_msg = str(e).lower()

            # Check if it's a cookie/auth error
            if any(
                keyword in error_msg
                for keyword in [
                    "unauthorized",
                    "forbidden",
                    "authentication",
                    "token",
                    "expired",
                    "401",
                    "403",
                ]
            ):
                raise CookieExpiredError(
                    f"Authentication failed. Cookies may be expired. Please update your cookies."
                )

            # Network/connection errors - retry
            if any(
                keyword in error_msg
                for keyword in [
                    "connection",
                    "timeout",
                    "network",
                    "unreachable",
                    "timed out",
                ]
            ):
                if attempt < MAX_NETWORK_RETRIES - 1:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    if retry_callback:
                        retry_callback(
                            f"🔌 Network error. Retrying in {delay}s... (Attempt {attempt + 1}/{MAX_NETWORK_RETRIES})"
                        )

                    # Sleep with stop checking
                    for _ in range(delay):
                        if should_stop_callback and should_stop_callback():
                            raise asyncio.CancelledError(
                                "Authentication stopped by user"
                            )
                        await asyncio.sleep(1)
                    continue
                else:
                    raise NetworkError(
                        f"Network connection failed after {MAX_NETWORK_RETRIES} attempts. Please check your connection."
                    )

            # Other errors
            raise TwitterScraperError(f"Authentication failed: {e}")

    raise NetworkError("Failed to authenticate after maximum retries")


async def handle_network_retry(
    operation, progress_callback=None, cookie_expired_callback=None
):
    """
    Wrapper for operations that may fail due to network or cookie issues.
    Implements automatic retry with exponential backoff.
    """
    for attempt in range(MAX_NETWORK_RETRIES):
        try:
            return await operation()

        except CookieExpiredError as e:
            # Cookie errors can't be auto-retried - need user intervention
            if cookie_expired_callback:
                cookie_expired_callback(str(e))
            raise

        except Exception as e:
            error_msg = str(e).lower()

            # Check if it's a network/connection error
            is_network_error = any(
                keyword in error_msg
                for keyword in [
                    "connection",
                    "timeout",
                    "network",
                    "unreachable",
                    "timed out",
                    "connection reset",
                    "connection refused",
                    "temporary failure",
                ]
            )

            if is_network_error and attempt < MAX_NETWORK_RETRIES - 1:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                if progress_callback:
                    progress_callback(
                        f"🔌 Network error detected. Retrying in {delay}s... "
                        f"(Attempt {attempt + 1}/{MAX_NETWORK_RETRIES})"
                    )
                await asyncio.sleep(delay)
                continue

            # Not a network error or max retries reached
            raise

    raise NetworkError("Operation failed after maximum network retries")


def validate_date_range(start_date: str, end_date: str) -> tuple:
    """Validate and parse date range - handles both YYYY-MM-DD and YYYY-MM-DD_HH:MM:SS formats."""
    try:
        # Handle dates that may include time (YYYY-MM-DD_HH:MM:SS format)
        start_dt = None
        end_dt = None

        if start_date:
            # Split date and time if present
            if "_" in start_date:
                date_part = start_date.split("_")[0]
            else:
                date_part = start_date
            start_dt = datetime.strptime(date_part, "%Y-%m-%d")

        if end_date:
            # Split date and time if present
            if "_" in end_date:
                date_part = end_date.split("_")[0]
            else:
                date_part = end_date
            end_dt = datetime.strptime(date_part, "%Y-%m-%d")

        today = datetime.now()

        # Validate future dates
        if end_dt and end_dt > today:
            logger.warning(f"End date is in the future. Using today's date.")
            end_dt = today

        if start_dt and end_dt and start_dt > end_dt:
            raise TwitterScraperError("Start date cannot be after end date.")

        return start_dt, end_dt
    except ValueError as e:
        raise TwitterScraperError(
            f"Invalid date format. Use YYYY-MM-DD (got error: {e})"
        )


def build_search_query(
    username: str = None,
    keywords: list = None,
    start_date: str = None,
    end_date: str = None,
    use_and: bool = False,
) -> str:
    """Build Twitter search query from parameters."""
    if not (username or keywords):
        raise TwitterScraperError("Either username or keywords must be provided.")

    if username:
        # Remove @ if present and validate username
        username = username.strip().lstrip("@")
        if not username.isalnum() and "_" not in username:
            raise TwitterScraperError(f"Invalid username format: {username}")
        query = f"(from:{username}) -filter:replies"
    else:
        # Clean and validate keywords
        clean_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not clean_keywords:
            raise TwitterScraperError("No valid keywords provided.")

        operator = " AND " if use_and else " OR "
        keyword_query = operator.join([f'"{kw}"' for kw in clean_keywords])
        query = f"({keyword_query}) -filter:replies"

    # Add date filters
    if start_date:
        # If date contains time (YYYY-MM-DD_HH:MM:SS), extract only date part
        if "_" in start_date:
            start_date = start_date.split("_")[0]
        query += f" since:{start_date}"

    if end_date:
        # If date contains time (YYYY-MM-DD_HH:MM:SS), extract only date part
        if "_" in end_date:
            end_date = end_date.split("_")[0]
        query += f" until:{end_date}"

    return query


def extract_tweet_data(tweet) -> dict:
    """Extract and normalize tweet data with better error handling for different tweet object types."""
    try:
        # Parse creation date with better error handling
        created_at = getattr(tweet, "created_at", "") or getattr(
            tweet, "created_at_datetime", ""
        )
        try:
            if created_at:
                if isinstance(created_at, str):
                    dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                else:
                    dt = created_at  # Already a datetime object
                formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract user information safely - handle different tweet object structures
        user = getattr(tweet, "user", None)
        if not user:
            # Try alternative attribute names
            user = getattr(tweet, "author", None)

        username = ""
        display_name = ""
        if user:
            username = getattr(user, "screen_name", "") or getattr(user, "username", "")
            display_name = getattr(user, "name", "")

        # Extract text - try multiple possible attributes
        text = getattr(tweet, "text", "") or getattr(tweet, "full_text", "")
        if text:
            text = text.replace("\n", " ").replace("\r", " ")

        # Extract tweet ID
        tweet_id = getattr(tweet, "id", "") or getattr(tweet, "id_str", "")

        # FIXED: Extract views count - using simple view_count attribute
        views = 0

        try:
            # Primary method: Simple view_count attribute (this is what works!)
            if hasattr(tweet, "view_count"):
                views = int(tweet.view_count) if tweet.view_count else 0
            # Fallback: view_count_state for newer versions
            elif hasattr(tweet, "view_count_state") and tweet.view_count_state:
                if isinstance(tweet.view_count_state, dict):
                    views = int(tweet.view_count_state.get("count", 0))
                else:
                    views = int(tweet.view_count_state)
            # Fallback: views dictionary
            elif hasattr(tweet, "views") and tweet.views:
                if isinstance(tweet.views, dict):
                    views = int(tweet.views.get("count", 0))
                else:
                    views = int(tweet.views)
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Could not extract views for tweet {tweet_id}: {e}")
            views = 0

        # Extract tweet metrics safely with multiple fallback attempts
        data = {
            "date": formatted_date,
            "username": username,
            "display_name": display_name,
            "text": text,
            "retweets": getattr(tweet, "retweet_count", 0) or 0,
            "likes": getattr(tweet, "favorite_count", 0)
            or getattr(tweet, "like_count", 0)
            or 0,
            "replies": getattr(tweet, "reply_count", 0) or 0,
            "quotes": getattr(tweet, "quote_count", 0) or 0,
            "views": views,
            "tweet_id": tweet_id,
            "tweet_url": (
                f"https://twitter.com/{username}/status/{tweet_id}"
                if username and tweet_id
                else ""
            ),
        }

        # Validate that we got at least some data
        if not data["tweet_id"] or not data["text"]:
            logger.warning(
                f"Tweet missing critical data - ID: {data['tweet_id']}, has text: {bool(data['text'])}"
            )
            return None

        return data

    except Exception as e:
        logger.warning(f"Error extracting tweet data: {e}")
        return None


def sanitize_worksheet_name(name: str) -> str:
    """
    Intelligently sanitize worksheet name to comply with Excel naming rules.
    Removes emojis, special characters, and invalid Excel characters while preserving readability.
    """
    import re

    # Remove emojis and special unicode characters
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags (iOS)
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "\U0001f900-\U0001f9ff"  # Supplemental Symbols and Pictographs
        "\U0001fa70-\U0001faff"  # Symbols and Pictographs Extended-A
        "]+",
        flags=re.UNICODE,
    )

    # Remove emojis
    name = emoji_pattern.sub("", name)

    # Excel worksheet names cannot contain these characters
    invalid_chars = ["\\", "/", "*", "[", "]", ":", "?"]

    # Replace problematic characters that often appear in usernames
    replacements = {
        "|": "-",
        "(": "",
        ")": "",
        "<": "",
        ">": "",
        '"': "",
        "{": "",
        "}": "",
        "&": "and",
    }

    sanitized = name

    # Apply replacements
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)

    # Remove invalid Excel characters
    for char in invalid_chars:
        sanitized = sanitized.replace(char, "_")

    # Remove any remaining non-ASCII or control characters
    sanitized = "".join(
        char for char in sanitized if ord(char) >= 32 and ord(char) < 127
    )

    # Clean up multiple spaces/underscores
    sanitized = re.sub(r"[\s_]+", "_", sanitized)

    # Remove leading/trailing underscores and spaces
    sanitized = sanitized.strip("_ ")

    # Excel worksheet names must be 31 characters or less
    if len(sanitized) > 31:
        sanitized = sanitized[:31].rstrip("_")

    # Cannot be empty - use fallback
    if not sanitized:
        sanitized = f"Tweets_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    return sanitized


def should_include_tweet(
    tweet_data: dict, keywords: list = None, use_and: bool = False
) -> bool:
    """Check if tweet should be included based on keyword filters."""
    if not keywords:
        return True

    text_lower = tweet_data["text"].lower()
    matches = [keyword.lower() in text_lower for keyword in keywords]

    if use_and:
        return all(matches)
    else:
        return any(matches)


async def take_custom_break(
    break_settings: dict,
    current_count: int,
    progress_callback=None,
    should_stop_callback=None,
):
    """
    Take a random break based on user settings.
    This is different from the rate limit break - it's a preventive measure.
    """
    if not break_settings or not break_settings.get("enabled"):
        return

    tweet_interval = break_settings.get("tweet_interval", 100)

    # Check if we should take a break
    if current_count > 0 and current_count % tweet_interval == 0:
        min_minutes = break_settings.get("min_break_minutes", 5)
        max_minutes = break_settings.get("max_break_minutes", 10)

        # Random break duration
        break_minutes = random.randint(min_minutes, max_minutes)
        break_seconds = break_minutes * 60

        if progress_callback:
            progress_callback(
                f"☕ Taking a {break_minutes}-minute break to avoid rate limits... "
                f"({current_count} tweets scraped)"
            )

        # Countdown with updates
        for remaining in range(break_seconds, 0, -1):
            if should_stop_callback and should_stop_callback():
                raise asyncio.CancelledError("Stopped during custom break")

            await asyncio.sleep(1)

            # Update progress every 30 seconds
            if remaining % 30 == 0:
                minutes, seconds = divmod(remaining, 60)
                if progress_callback:
                    progress_callback(
                        f"☕ Custom break in progress... Resuming in {minutes:02d}:{seconds:02d}"
                    )

        if progress_callback:
            progress_callback("🔄 Break complete! Resuming scraping...")


async def scrape_tweets(
    username: str = None,
    start_date: str = None,
    end_date: str = None,
    keywords: list = None,
    use_and: bool = False,
    export_format: str = "excel",
    save_dir: str = DEFAULT_EXPORT_DIR,
    progress_callback=None,
    should_stop_callback=None,
    cookie_expired_callback=None,
    network_error_callback=None,  # NEW
    save_every_n: int = 50,
    max_tweets: int = None,
    break_settings: dict = None,
    resume_state: dict = None,
):
    """
    Scrape tweets from a username or keyword search and export them.

    New parameters:
        cookie_expired_callback: Function to call when cookies expire (pauses scraping)
        resume_state: Dictionary with resume information (from StateManager)
    """

    csv_file = None
    wb = None
    ws = None

    try:
        # Check if resuming
        resuming = resume_state is not None
        if resuming:
            if progress_callback:
                progress_callback(f"🔄 Resuming from previous session...")
            count = resume_state.get("tweets_scraped", 0)
            seen_tweet_ids = set(resume_state.get("seen_tweet_ids", []))
            output_path = resume_state.get("output_path")

            # Re-open existing file for append
            if export_format.lower() == "csv":
                csv_file = open(output_path, mode="a", newline="", encoding="utf-8")
                writer = csv.writer(csv_file)
            else:
                wb = load_workbook(output_path)
                ws = wb.active
        else:
            # New scrape - validate and setup
            validate_date_range(start_date, end_date)
            count = 0
            seen_tweet_ids = set()

            # Setup export file
            os.makedirs(save_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"{username or 'keywords'}_{timestamp}"
            ext = "csv" if export_format.lower() == "csv" else "xlsx"
            output_path = os.path.join(save_dir, f"{base_filename}.{ext}")

            headers = [
                "Date",
                "Username",
                "Display Name",
                "Text",
                "Retweets",
                "Likes",
                "Replies",
                "Quotes",
                "Views",
                "Tweet ID",
                "Tweet URL",
                "Export Path",
            ]

            # Initialize export file
            if export_format.lower() == "csv":
                csv_file = open(output_path, mode="w", newline="", encoding="utf-8")
                writer = csv.writer(csv_file)
                writer.writerow(headers)
            else:
                wb = Workbook()
                ws = wb.active
                # Sanitize worksheet name
                if username:
                    ws.title = sanitize_worksheet_name(username)
                elif keywords:
                    ws.title = sanitize_worksheet_name("_".join(keywords[:3]))
                else:
                    ws.title = "Tweets"
                ws.append(headers)

        query = build_search_query(username, keywords, start_date, end_date, use_and)

        if progress_callback and not resuming:
            progress_callback(f"🔍 Search query: {query}")

        # Authenticate with retry logic
        if progress_callback:
            progress_callback("🔑 Authenticating...")

        client = await authenticate(
            retry_callback=progress_callback, should_stop_callback=should_stop_callback
        )

        # Check if stopped after authentication
        if should_stop_callback and should_stop_callback():
            if progress_callback:
                progress_callback("🛑 Stopped after authentication")
            return output_path, count, list(seen_tweet_ids)

        if progress_callback:
            progress_callback("🔍 Starting tweet search...")

        # Start search with network retry wrapper
        async def start_search():
            return await client.search_tweet(query, product="Latest")

        page = await handle_network_retry(
            start_search,
            progress_callback=progress_callback,
            cookie_expired_callback=cookie_expired_callback,
        )

        duplicate_count = 0
        empty_page_count = 0  # NEW: Track consecutive empty pages
        MAX_EMPTY_PAGES = 3  # NEW: Stop after 3 empty pages

        try:
            while page:
                if should_stop_callback and should_stop_callback():
                    if progress_callback:
                        progress_callback("⚠️ Stopping scrape...")
                    break

                page_tweets = 0
                for tweet in page:
                    if should_stop_callback and should_stop_callback():
                        break

                    if max_tweets and count >= max_tweets:
                        if progress_callback:
                            progress_callback(
                                f"📊 Reached maximum tweet limit: {max_tweets}"
                            )
                        break

                    tweet_data = extract_tweet_data(tweet)
                    if not tweet_data:
                        continue

                    tweet_id = tweet_data["tweet_id"]
                    if tweet_id in seen_tweet_ids:
                        duplicate_count += 1
                        continue
                    seen_tweet_ids.add(tweet_id)

                    if not should_include_tweet(tweet_data, keywords, use_and):
                        continue

                    row = [
                        tweet_data["date"],
                        tweet_data["username"],
                        tweet_data["display_name"],
                        tweet_data["text"],
                        tweet_data["retweets"],
                        tweet_data["likes"],
                        tweet_data["replies"],
                        tweet_data["quotes"],
                        tweet_data["views"],
                        tweet_data["tweet_id"],
                        tweet_data["tweet_url"],
                        os.path.abspath(output_path),
                    ]

                    if export_format.lower() == "csv":
                        writer.writerow(row)
                    else:
                        ws.append(row)

                    count += 1
                    page_tweets += 1

                    if progress_callback:
                        progress_callback(count)

                    if count % save_every_n == 0:
                        if export_format.lower() == "csv":
                            csv_file.flush()
                        else:
                            wb.save(output_path)

                        if progress_callback:
                            progress_callback(f"💾 Auto-saved {count} tweets")

                    await take_custom_break(
                        break_settings, count, progress_callback, should_stop_callback
                    )

                # NEW: Track empty pages
                # Smart empty page handling
                if page_tweets == 0:
                    empty_page_count += 1

                    if progress_callback:
                        progress_callback(
                            f"📭 Empty page {empty_page_count} (found {count} tweets so far)"
                        )

                    # SMART DECISION MAKING
                    if count == 0 and empty_page_count >= 3:
                        # No tweets found at all after 3 pages - likely no results
                        if progress_callback:
                            progress_callback(
                                "❌ No tweets found matching your criteria"
                            )
                        break

                    elif empty_page_count == EMPTY_PAGE_PROMPT_THRESHOLD:
                        # We've found tweets but now hitting empty pages - ask user
                        if progress_callback:
                            progress_callback(
                                f"⚠️ Hit {EMPTY_PAGE_PROMPT_THRESHOLD} consecutive empty pages after finding {count} tweets. "
                                "This could be a gap in the timeline or end of results."
                            )

                        # This will trigger a GUI prompt
                        raise EmptyPagePromptException(
                            f"Hit {empty_page_count} empty pages. Found {count} tweets so far."
                        )

                    elif empty_page_count >= MAX_CONSECUTIVE_EMPTY_PAGES:
                        # Too many empty pages - stop
                        if progress_callback:
                            progress_callback(
                                f"✅ Stopping after {empty_page_count} consecutive empty pages. "
                                f"Collected {count} tweets total."
                            )
                        break

                else:
                    # Found tweets - reset counter
                    if empty_page_count > 0 and progress_callback:
                        progress_callback(
                            f"✅ Found more tweets after {empty_page_count} empty pages"
                        )
                    empty_page_count = 0

                # NEW: Improved pagination with retry logic
                pagination_retry = 0
                while pagination_retry < MAX_PAGINATION_RETRIES:
                    try:
                        if progress_callback:
                            progress_callback(
                                f"📄 Loading next page... ({count} tweets so far)"
                            )

                        page = await page.next()
                        break  # Success, exit retry loop

                    except StopAsyncIteration:
                        if progress_callback:
                            progress_callback("✅ Reached end of results")
                        page = None
                        break

                    except TooManyRequests:
                        if progress_callback:
                            progress_callback(
                                "⏳ RATE LIMIT HIT! Waiting 15 minutes... (Twitter's rate limit)"
                            )

                        for remaining in range(900, 0, -1):
                            if should_stop_callback and should_stop_callback():
                                raise asyncio.CancelledError(
                                    "Stopped during rate limit wait"
                                )
                            await asyncio.sleep(1)

                            if remaining % 30 == 0:
                                minutes, seconds = divmod(remaining, 60)
                                if progress_callback:
                                    progress_callback(
                                        f"⏳ Rate limit countdown: {minutes:02d}:{seconds:02d} remaining"
                                    )

                        if progress_callback:
                            progress_callback(
                                "🔄 Rate limit wait complete. Resuming..."
                            )
                        pagination_retry += 1
                        continue

                    except Exception as e:
                        error_msg = str(e).lower()

                        # NEW: Check for authentication errors
                        # Check for authentication errors
                        if any(
                            keyword in error_msg
                            for keyword in [
                                "unauthorized",
                                "forbidden",
                                "401",
                                "403",
                                "token",
                                "authentication",
                            ]
                        ):
                            if progress_callback:
                                progress_callback("🔑 Authentication error detected")
                            if cookie_expired_callback:
                                cookie_expired_callback(
                                    "Session expired during pagination"
                                )
                            # Retry this page after cookies updated
                            pagination_retry += 1
                            continue

                        # Check for network errors
                        if any(
                            keyword in error_msg
                            for keyword in [
                                "connection",
                                "timeout",
                                "network",
                                "unreachable",
                                "getaddrinfo",  # ADD - Your specific error
                                "11001",  # ADD - Your error code
                                "errno 11001",  # ADD - Full error
                                "name resolution",  # ADD
                                "connection reset",
                                "connection refused",
                                "temporary failure",
                            ]
                        ):
                            if pagination_retry < MAX_PAGINATION_RETRIES - 1:
                                if network_error_callback:
                                    network_error_callback(
                                        f"Network error during pagination: {error_msg}"
                                    )
                                # Callback will pause and wait for reconnection
                                pagination_retry += 1
                                continue
                            else:
                                raise NetworkError(
                                    "Network connection failed during pagination after retries"
                                )

                        # 404 or other errors
                        if "404" in error_msg or "not found" in error_msg:
                            if pagination_retry < MAX_PAGINATION_RETRIES - 1:
                                if progress_callback:
                                    progress_callback(
                                        f"⚠️ Pagination 404 (attempt {pagination_retry + 1}/{MAX_PAGINATION_RETRIES}). Retrying..."
                                    )
                                await asyncio.sleep(5)
                                pagination_retry += 1
                                continue
                            else:
                                if progress_callback:
                                    progress_callback(
                                        "📭 No more pages available (404 after retries)"
                                    )
                                page = None
                                break

                        # Unknown error
                        logger.error(f"Pagination error: {e}")
                        if progress_callback:
                            progress_callback(f"⚠️ Pagination error: {e}")
                        page = None
                        break

                if page is None:
                    break

        except asyncio.CancelledError:
            if progress_callback:
                progress_callback("🛑 Scrape cancelled by user")
            raise

        finally:
            # Final save
            if export_format.lower() == "csv" and csv_file:
                csv_file.close()
            elif wb:
                wb.save(output_path)

        # Summary
        if progress_callback:
            summary = f"✅ Scrape complete: {count} tweets"
            if duplicate_count > 0:
                summary += f" ({duplicate_count} duplicates skipped)"
            progress_callback(summary)

        return output_path, count, list(seen_tweet_ids)

    except CookieExpiredError:
        # Save state happens in GUI - just propagate the error
        if progress_callback:
            progress_callback("🔑 Cookie expired - please update cookies to continue")
        raise

    except NetworkError:
        # Save state happens in GUI - just propagate the error
        if progress_callback:
            progress_callback("🔌 Network error - please check connection and resume")
        raise

    except Exception as e:
        logger.error(f"Scrape error: {e}")
        raise TwitterScraperError(f"Scraping failed: {e}")

    finally:
        # Ensure files are closed
        if csv_file and not csv_file.closed:
            csv_file.close()


async def scrape_multiple_usernames(
    usernames: list,
    start_date: str,
    end_date: str,
    export_format: str = "excel",
    save_dir: str = DEFAULT_EXPORT_DIR,
    progress_callback=None,
    should_stop_callback=None,
    cookie_expired_callback=None,
    max_tweets_per_user: int = None,
    break_settings: dict = None,
):
    """Batch scrape multiple usernames with improved error handling and resume support."""
    if not usernames:
        raise TwitterScraperError("No usernames provided for batch scraping.")

    results = []
    total_tweets = 0

    for i, username in enumerate(usernames, 1):
        if should_stop_callback and should_stop_callback():
            if progress_callback:
                progress_callback("🛑 Batch scrape stopped by user")
            break

        clean_username = username.strip().lstrip("@")
        if not clean_username:
            continue

        if progress_callback:
            progress_callback(
                f"👤 Processing user {i}/{len(usernames)}: @{clean_username}"
            )

        try:
            output_path, count, seen_ids = await scrape_tweets(
                username=clean_username,
                start_date=start_date,
                end_date=end_date,
                export_format=export_format,
                save_dir=save_dir,
                progress_callback=progress_callback,
                should_stop_callback=should_stop_callback,
                cookie_expired_callback=cookie_expired_callback,
                max_tweets=max_tweets_per_user,
                break_settings=break_settings,
            )

            results.append(
                {
                    "username": clean_username,
                    "output_path": output_path,
                    "tweet_count": count,
                    "status": "success",
                }
            )

            total_tweets += count

            if progress_callback:
                progress_callback(f"✅ @{clean_username}: {count} tweets saved")

        except CookieExpiredError as e:
            # Propagate cookie errors to GUI for handling
            raise

        except NetworkError as e:
            # Propagate network errors to GUI for handling
            raise

        except Exception as e:
            error_msg = str(e)
            results.append(
                {
                    "username": clean_username,
                    "output_path": None,
                    "tweet_count": 0,
                    "status": "failed",
                    "error": error_msg,
                }
            )

            if progress_callback:
                progress_callback(f"❌ @{clean_username} failed: {error_msg}")

            logger.error(f"Failed to scrape @{clean_username}: {e}")

    if progress_callback:
        successful = len([r for r in results if r["status"] == "success"])
        progress_callback(
            f"🎉 Batch complete: {successful}/{len(usernames)} users, {total_tweets} total tweets"
        )

    return results


async def scrape_tweet_links_file(
    file_path: str,
    export_format: str = "excel",
    save_dir: str = DEFAULT_EXPORT_DIR,
    progress_callback=None,
    should_stop_callback=None,
    cookie_expired_callback=None,
    network_error_callback=None,  # NEW
    break_settings: dict = None,
    resume_state: dict = None,
):
    """
    Scrape tweet details directly from a file of tweet links (.txt or .xlsx/.xls).
    Now supports resume from saved state.
    """

    csv_file = None
    wb = None
    ws = None
    client = None

    try:
        # Check if resuming
        resuming = resume_state is not None

        if resuming:
            if progress_callback:
                progress_callback("🔄 Resuming link scrape from previous session...")

            # Load resume data
            file_path = resume_state.get("links_file_path")
            output_path = resume_state.get("output_path")
            count = resume_state.get("tweets_scraped", 0)
            failed = resume_state.get("failed_count", 0)
            skipped_no_data = resume_state.get("skipped_no_data", 0)
            current_index = resume_state.get("current_index", 0)
            processed_links = set(resume_state.get("processed_links", []))

            # Re-open existing file for append
            if export_format.lower() == "csv":
                csv_file = open(output_path, mode="a", newline="", encoding="utf-8")
                writer = csv.writer(csv_file)
            else:
                wb = load_workbook(output_path)
                ws = wb.active
        else:
            # New scrape - validate file
            if not os.path.exists(file_path):
                raise TwitterScraperError(f"File not found: {file_path}")

            count = 0
            failed = 0
            skipped_no_data = 0
            current_index = 0
            processed_links = set()

            # Setup export file
            os.makedirs(save_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"tweet_links_{timestamp}"
            ext_out = "csv" if export_format.lower() == "csv" else "xlsx"
            output_path = os.path.join(save_dir, f"{base_filename}.{ext_out}")

            headers = [
                "Date",
                "Username",
                "Display Name",
                "Text",
                "Retweets",
                "Likes",
                "Replies",
                "Quotes",
                "Views",
                "Tweet ID",
                "Tweet URL",
                "Export Path",
            ]

            # Initialize file
            if export_format.lower() == "csv":
                csv_file = open(output_path, mode="w", newline="", encoding="utf-8")
                writer = csv.writer(csv_file)
                writer.writerow(headers)
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = "Tweets"
                ws.append(headers)

        # Load links from file
        ext = os.path.splitext(file_path)[1].lower()
        links = []

        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path, header=None)
            links = df.iloc[:, 0].dropna().astype(str).tolist()
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                links = [line.strip() for line in f if line.strip()]
        else:
            raise TwitterScraperError("Unsupported file type. Use .txt or .xlsx/.xls")

        if not links:
            raise TwitterScraperError("No tweet links found in the provided file.")

        # Validate and deduplicate links
        valid_links = []
        seen_links = set()
        invalid_count = 0

        for link in links:
            if link in seen_links or link in processed_links:
                continue

            if not TWEET_ID_PATTERN.match(link):
                invalid_count += 1
                logger.warning(f"Invalid tweet URL format: {link}")
                if progress_callback:
                    progress_callback(f"⚠️ Skipped invalid URL: {link}")
                continue

            valid_links.append(link)
            seen_links.add(link)

        if not valid_links:
            raise TwitterScraperError(
                f"No valid tweet links found. {invalid_count} links had invalid format."
            )

        # Authenticate
        if progress_callback:
            progress_callback("🔑 Authenticating Twikit client...")

        client = await authenticate(retry_callback=progress_callback)
        total_links = len(valid_links)

        # Skip already processed links if resuming
        if resuming:
            valid_links = valid_links[current_index:]
            if progress_callback:
                progress_callback(
                    f"📋 Resuming from link {current_index + 1}/{total_links}"
                )

        for i, link in enumerate(valid_links, current_index + 1):
            if should_stop_callback and should_stop_callback():
                if progress_callback:
                    progress_callback("🛑 Scrape cancelled by user")
                break

            if progress_callback:
                progress_callback(f"🔗 Processing link {i}/{total_links}")

            try:
                match = TWEET_ID_PATTERN.match(link)
                if not match:
                    failed += 1
                    logger.warning(f"Could not extract tweet ID from {link}")
                    continue

                tweet_id = match.group(1)

                # 🔧 FETCH BLOCK — EXACTLY AS INSTRUCTED
                try:
                    tweet = await client.get_tweet_by_id(tweet_id)

                except Exception as fetch_error:
                    error_msg = str(fetch_error).lower()

                    # Check for authentication errors
                    if any(
                        keyword in error_msg
                        for keyword in ["unauthorized", "forbidden", "401", "403"]
                    ):
                        raise CookieExpiredError("Session expired while scraping links")

                    # Check for network errors
                    if any(
                        keyword in error_msg
                        for keyword in ["connection", "timeout", "network"]
                    ):
                        raise NetworkError(
                            "Network connection failed while scraping links"
                        )

                    logger.warning(f"Failed to fetch tweet {tweet_id}: {fetch_error}")
                    failed += 1
                    processed_links.add(link)
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    continue
                # 🔧 END FETCH BLOCK

                tweet_data = extract_tweet_data(tweet)

                if not tweet_data:
                    skipped_no_data += 1
                    logger.info(f"No data extracted from tweet {tweet_id}")
                    if progress_callback:
                        progress_callback(
                            f"⏭️ Skipped tweet {tweet_id}: no data extracted"
                        )
                    processed_links.add(link)
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    continue

                row = [
                    tweet_data["date"],
                    tweet_data["username"],
                    tweet_data["display_name"],
                    tweet_data["text"],
                    tweet_data["retweets"],
                    tweet_data["likes"],
                    tweet_data["replies"],
                    tweet_data["quotes"],
                    tweet_data["views"],
                    tweet_data["tweet_id"],
                    tweet_data["tweet_url"],
                    os.path.abspath(output_path),
                ]

                if export_format.lower() == "csv":
                    writer.writerow(row)
                else:
                    ws.append(row)

                count += 1
                processed_links.add(link)

                if progress_callback:
                    progress_callback(f"✅ Scraped {count}/{total_links}")

                if count % 20 == 0:
                    if export_format.lower() == "csv":
                        csv_file.flush()
                    else:
                        wb.save(output_path)

                await asyncio.sleep(RATE_LIMIT_DELAY)
                await take_custom_break(
                    break_settings, count, progress_callback, should_stop_callback
                )

            except CookieExpiredError:
                raise

            except NetworkError:
                raise

            except Exception as e:
                failed += 1
                logger.warning(f"Failed to scrape {link}: {str(e)}")
                if progress_callback:
                    progress_callback(f"⚠️ Error on link {i}: {str(e)[:50]}")
                processed_links.add(link)
                await asyncio.sleep(2)

        # Final save
        if export_format.lower() == "csv":
            if csv_file:
                csv_file.close()
        else:
            wb.save(output_path)

        summary = f"🏁 Done: {count} scraped, {failed} failed, {skipped_no_data} skipped (no data)"
        if progress_callback:
            progress_callback(summary)

        logger.info(summary)
        return output_path, count, failed, list(processed_links)

    except CookieExpiredError:
        if progress_callback:
            progress_callback("🔑 Cookie expired - please update cookies to continue")
        raise

    except NetworkError:
        if progress_callback:
            progress_callback("🔌 Network error - please check connection and resume")
        raise

    except Exception as e:
        logger.error(f"Error scraping tweet links: {e}")
        raise TwitterScraperError(f"Scraping tweet links failed: {e}")

    finally:
        if csv_file and not csv_file.closed:
            csv_file.close()

        if client:
            try:
                if hasattr(client, "close"):
                    await client.close()
            except Exception as e:
                logger.warning(f"Error closing client: {e}")


# Utility functions for the GUI
def get_estimated_time(tweet_count: int) -> str:
    """Estimate scraping time based on tweet count."""
    if tweet_count < 100:
        return "< 1 minute"
    elif tweet_count < 1000:
        return f"{tweet_count // 100} minutes"
    else:
        return f"{tweet_count // 1000} hours"


def validate_username(username: str) -> bool:
    """Validate Twitter username format."""
    if not username:
        return False

    username = username.strip().lstrip("@")
    return username.replace("_", "").isalnum() and len(username) <= 15


def get_scrape_stats(output_path: str) -> dict:
    """Get statistics from scraped data file."""
    if not os.path.exists(output_path):
        return {}

    try:
        if output_path.endswith(".csv"):
            with open(output_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
                return {
                    "total_rows": len(rows) - 1,  # Exclude header
                    "file_size": os.path.getsize(output_path),
                    "created": datetime.fromtimestamp(os.path.getctime(output_path)),
                }
        # Add Excel stats if needed
        return {}
    except Exception:
        return {}
