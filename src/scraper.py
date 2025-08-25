import os
import json
import asyncio
import csv
from datetime import datetime, timezone
from twikit import Client, TooManyRequests
from openpyxl import Workbook
import logging

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


async def authenticate():
    """Authenticate Twikit client using stored cookies."""
    client = Client(language="en-US")

    if not os.path.exists(COOKIES_FILE):
        raise TwitterScraperError(
            f"Cookie file not found at {COOKIES_FILE}. Please save cookies first."
        )

    try:
        client.load_cookies(COOKIES_FILE)
        # Test authentication with a simple search
        test_result = await client.search_tweet("(from:twitter)", product="Latest")
        logger.info("Authentication successful")
        return client
    except Exception as e:
        raise TwitterScraperError(
            f"Authentication failed. Please update your cookies: {e}"
        )


def validate_date_range(start_date: str, end_date: str) -> tuple:
    """Validate and parse date range."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

        if start_dt and end_dt and start_dt > end_dt:
            raise TwitterScraperError("Start date cannot be after end date.")

        return start_dt, end_dt
    except ValueError as e:
        raise TwitterScraperError(f"Invalid date format. Use YYYY-MM-DD: {e}")


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
        query += f" since:{start_date}"
    if end_date:
        query += f" until:{end_date}"

    return query


def extract_tweet_data(tweet) -> dict:
    """Extract and normalize tweet data."""
    try:
        # Parse creation date with better error handling
        created_at = getattr(tweet, "created_at", "")
        try:
            if created_at:
                dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
                formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            formatted_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Extract user information safely
        user = getattr(tweet, "user", None)
        username = getattr(user, "screen_name", "") if user else ""
        display_name = getattr(user, "name", "") if user else ""

        # Extract tweet metrics safely
        data = {
            "date": formatted_date,
            "username": username,
            "display_name": display_name,
            "text": getattr(tweet, "text", "").replace("\n", " ").replace("\r", " "),
            "retweets": getattr(tweet, "retweet_count", 0) or 0,
            "likes": getattr(tweet, "favorite_count", 0) or 0,
            "replies": getattr(tweet, "reply_count", 0) or 0,
            "quotes": getattr(tweet, "quote_count", 0) or 0,
            "views": getattr(tweet, "view_count", 0) or 0,
            "tweet_id": getattr(tweet, "id", ""),
            "tweet_url": (
                f"https://twitter.com/{username}/status/{getattr(tweet, 'id', '')}"
                if username
                else ""
            ),
        }

        return data

    except Exception as e:
        logger.warning(f"Error extracting tweet data: {e}")
        return None


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


async def scrape_tweets(
    username: str = None,
    start_date: str = None,
    end_date: str = None,
    keywords: list = None,
    use_and: bool = False,
    export_format: str = "excel",
    save_dir: str = DEFAULT_EXPORT_DIR,  # Changed parameter name for clarity
    progress_callback=None,
    should_stop_callback=None,
    save_every_n: int = 50,  # Reduced for more frequent saves
    max_tweets: int = None,  # New: optional limit
):
    """Scrape tweets from a username or keyword search and export them."""

    try:
        # Validate inputs
        validate_date_range(start_date, end_date)
        query = build_search_query(username, keywords, start_date, end_date, use_and)

        if progress_callback:
            progress_callback(f"🔍 Search query: {query}")

        # Authenticate
        client = await authenticate()

        # Start search
        try:
            page = await client.search_tweet(query, product="Latest")
        except Exception as e:
            raise TwitterScraperError(f"Failed to start tweet search: {e}")

        # Setup export file
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"{username or 'keywords'}_{timestamp}"
        ext = "csv" if export_format.lower() == "csv" else "xlsx"
        output_path = os.path.join(save_dir, f"{base_filename}.{ext}")

        # Define headers
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
            ws.title = "Tweets"
            ws.append(headers)

        count = 0
        duplicate_count = 0
        seen_tweet_ids = set()

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

                    # Check max tweets limit
                    if max_tweets and count >= max_tweets:
                        if progress_callback:
                            progress_callback(
                                f"📊 Reached maximum tweet limit: {max_tweets}"
                            )
                        break

                    # Extract tweet data
                    tweet_data = extract_tweet_data(tweet)
                    if not tweet_data:
                        continue

                    # Check for duplicates
                    tweet_id = tweet_data["tweet_id"]
                    if tweet_id in seen_tweet_ids:
                        duplicate_count += 1
                        continue
                    seen_tweet_ids.add(tweet_id)

                    # Apply keyword filter
                    if not should_include_tweet(tweet_data, keywords, use_and):
                        continue

                    # Prepare row data
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

                    # Write to file
                    if export_format.lower() == "csv":
                        writer.writerow(row)
                    else:
                        ws.append(row)

                    count += 1
                    page_tweets += 1

                    if progress_callback:
                        progress_callback(count)

                    # Auto-save periodically
                    if count % save_every_n == 0:
                        if export_format.lower() == "csv":
                            csv_file.flush()
                        else:
                            wb.save(output_path)

                        if progress_callback:
                            progress_callback(f"💾 Auto-saved {count} tweets")

                # Check if we got any tweets from this page
                if page_tweets == 0:
                    if progress_callback:
                        progress_callback("📭 No more relevant tweets found")
                    break

                # Pagination
                try:
                    if progress_callback:
                        progress_callback(
                            f"📄 Loading next page... ({count} tweets so far)"
                        )
                    page = await page.next()

                except StopAsyncIteration:
                    if progress_callback:
                        progress_callback("✅ Reached end of results")
                    break

                except TooManyRequests:
                    if progress_callback:
                        progress_callback(
                            "⏳ Rate limit reached. Waiting 15 minutes..."
                        )

                    # Wait with countdown
                    for remaining in range(900, 0, -1):
                        if should_stop_callback and should_stop_callback():
                            raise asyncio.CancelledError(
                                "Stopped during rate limit wait"
                            )

                        await asyncio.sleep(1)

                        # Update progress every 30 seconds
                        if remaining % 30 == 0:
                            minutes, seconds = divmod(remaining, 60)
                            if progress_callback:
                                progress_callback(
                                    f"⏳ Resuming in {minutes:02d}:{seconds:02d}"
                                )

                    if progress_callback:
                        progress_callback("🔄 Resuming scrape...")
                    continue

                except Exception as e:
                    logger.error(f"Pagination error: {e}")
                    if progress_callback:
                        progress_callback(f"⚠️ Pagination error: {e}")
                    break

        except asyncio.CancelledError:
            if progress_callback:
                progress_callback("🛑 Scrape cancelled by user")
            raise

        finally:
            # Final save
            if export_format.lower() == "csv":
                csv_file.close()
            else:
                wb.save(output_path)

        # Summary
        if progress_callback:
            summary = f"✅ Scrape complete: {count} tweets"
            if duplicate_count > 0:
                summary += f" ({duplicate_count} duplicates skipped)"
            progress_callback(summary)

        return output_path, count

    except Exception as e:
        logger.error(f"Scrape error: {e}")
        raise TwitterScraperError(f"Scraping failed: {e}")


async def scrape_multiple_usernames(
    usernames: list,
    start_date: str,
    end_date: str,
    export_format: str = "excel",
    save_dir: str = DEFAULT_EXPORT_DIR,
    progress_callback=None,
    should_stop_callback=None,
    max_tweets_per_user: int = None,
):
    """Batch scrape multiple usernames with improved error handling."""
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
            output_path, count = await scrape_tweets(
                username=clean_username,
                start_date=start_date,
                end_date=end_date,
                export_format=export_format,
                save_dir=save_dir,
                progress_callback=progress_callback,
                should_stop_callback=should_stop_callback,
                max_tweets=max_tweets_per_user,
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
