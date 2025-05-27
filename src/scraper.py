import os
import json
import asyncio
import csv
from datetime import datetime
from twikit import Client, TooManyRequests
from openpyxl import Workbook

# Paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COOKIES_FILE = os.path.join(BASE_DIR, "cookies", "twikit_cookies.json")
EXPORT_DIR = os.path.join(BASE_DIR, "data", "exports")


async def authenticate():
    client = Client(language="en-US")
    if not os.path.exists(COOKIES_FILE):
        raise FileNotFoundError(f"Cookie file not found at {COOKIES_FILE}.")
    try:
        client.load_cookies(COOKIES_FILE)
        await client.search_tweet("(from:jack)", product="Latest")
    except Exception as e:
        raise RuntimeError(f"Authentication failed: {e}")
    return client


async def scrape_tweets(
    username: str = None,
    start_date: str = None,
    end_date: str = None,
    keywords: list = None,
    use_and: bool = False,
    export_format: str = "excel",
    progress_callback=None,
    should_stop_callback=None,
    save_every_n: int = 100,
):
    if not (username or keywords):
        raise ValueError("Either username or keywords must be provided.")

    if username:
        query = f"(from:{username}) -filter:replies"
    else:
        q = " OR ".join([f'"{kw.strip()}"' for kw in keywords if kw.strip()])
        if not q:
            raise ValueError("Keyword query is empty.")
        query = f"({q}) -filter:replies"

    if start_date:
        query += f" since:{start_date}"
    if end_date:
        query += f" until:{end_date}"

    client = await authenticate()
    try:
        page = await client.search_tweet(query, product="Latest")
    except Exception as e:
        raise RuntimeError(f"Failed to start tweet search: {e}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{username or 'keywords'}_{timestamp}"
    ext = "csv" if export_format == "csv" else "xlsx"
    output_path = os.path.join(EXPORT_DIR, f"{base_filename}.{ext}")
    os.makedirs(EXPORT_DIR, exist_ok=True)

    if export_format == "csv":
        csv_file = open(output_path, mode="w", newline="", encoding="utf-8")
        writer = csv.writer(csv_file)
        writer.writerow(["Date", "Username", "Text", "Retweets", "Likes", "Views"])
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Tweets"
        ws.append(["Date", "Username", "Text", "Retweets", "Likes", "Views"])

    count = 0

    try:
        while page:
            if should_stop_callback and should_stop_callback():
                break

            for tweet in page:
                if should_stop_callback and should_stop_callback():
                    break

                try:
                    dt = datetime.strptime(tweet.created_at, "%a %b %d %H:%M:%S %z %Y")
                except Exception:
                    continue

                if keywords:
                    text = getattr(tweet, "text", "").lower()
                    matches = [kw.lower() in text for kw in keywords]
                    if use_and and not all(matches):
                        continue
                    if not use_and and not any(matches):
                        continue

                row = [
                    dt.strftime("%Y-%m-%d %H:%M:%S"),
                    getattr(tweet.user, "name", ""),
                    getattr(tweet, "text", ""),
                    getattr(tweet, "retweet_count", 0),
                    getattr(tweet, "favorite_count", 0),
                    getattr(tweet, "view_count", 0),
                ]

                if export_format == "csv":
                    writer.writerow(row)
                else:
                    ws.append(row)

                count += 1
                if progress_callback:
                    progress_callback(count)

                if count and count % save_every_n == 0:
                    if export_format == "csv":
                        csv_file.flush()
                    else:
                        wb.save(output_path)
                    if progress_callback:
                        progress_callback(f"Auto-saved at {count} tweets")

            try:
                page = await page.next()
            except StopAsyncIteration:
                break
            except TooManyRequests:
                if progress_callback:
                    progress_callback("Rate limit hit. Sleeping 15m…")
                for sec in range(900, 0, -1):
                    if should_stop_callback and should_stop_callback():
                        raise asyncio.CancelledError()
                    await asyncio.sleep(1)
                    if progress_callback and sec % 60 == 0:
                        m, s = divmod(sec, 60)
                        progress_callback(f"Resuming in {m:02d}:{s:02d}")
                continue

    except asyncio.CancelledError:
        pass

    finally:
        if export_format == "csv":
            csv_file.close()
        else:
            wb.save(output_path)

    return output_path, count


# 🆕 New: Multi-username batch mode
async def scrape_multiple_usernames(
    usernames: list,
    start_date: str,
    end_date: str,
    export_format: str = "excel",
    progress_callback=None,
    should_stop_callback=None,
):
    results = []
    for i, user in enumerate(usernames):
        if should_stop_callback and should_stop_callback():
            break
        if progress_callback:
            progress_callback(f"🔄 Scraping {user} ({i+1}/{len(usernames)})...")
        try:
            output, count = await scrape_tweets(
                username=user,
                start_date=start_date,
                end_date=end_date,
                keywords=None,
                use_and=False,
                export_format=export_format,
                progress_callback=progress_callback,
                should_stop_callback=should_stop_callback,
            )
            results.append((user, output, count))
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ Error scraping {user}: {e}")
    return results
