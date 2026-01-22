"""
Features Module - Additional utilities for the Tweet Scraper.

Contains:
- Settings persistence (remember last settings)
- Scrape history logging
- Analytics calculations
- Filter definitions
- Cost estimation
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from collections import Counter


# ========================================
# PATHS
# ========================================
def get_data_dir():
    """Get the data directory for storing app data."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_settings_path():
    return os.path.join(get_data_dir(), "user_settings.json")


def get_history_path():
    return os.path.join(get_data_dir(), "scrape_history.json")


# ========================================
# USER SETTINGS (Remember Last Settings)
# ========================================
@dataclass
class UserSettings:
    """Persistent user settings."""
    # Last used values
    last_username: str = ""
    last_keywords: str = ""
    last_mode: str = "Username"  # "Username" or "Keywords"
    last_start_date: str = ""
    last_end_date: str = ""
    last_export_format: str = "Excel"
    last_save_dir: str = ""
    last_scraping_method: str = "cookie"
    
    # Preferences
    enable_breaks: bool = False
    break_interval: int = 100
    break_min: int = 5
    break_max: int = 10
    
    # Filter defaults
    min_likes: int = 0
    min_retweets: int = 0
    exclude_retweets: bool = False
    exclude_replies: bool = True
    media_only: bool = False
    
    # Window position (optional)
    window_x: int = -1
    window_y: int = -1


class SettingsManager:
    """Manage persistent user settings."""
    
    def __init__(self):
        self.settings = UserSettings()
        self.load()
    
    def load(self) -> UserSettings:
        """Load settings from file."""
        path = get_settings_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, value in data.items():
                        if hasattr(self.settings, key):
                            setattr(self.settings, key, value)
            except Exception:
                pass
        return self.settings
    
    def save(self):
        """Save settings to file."""
        path = get_settings_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.settings), f, indent=2)
        except Exception:
            pass
    
    def update(self, **kwargs):
        """Update specific settings."""
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self.save()


# ========================================
# SCRAPE HISTORY
# ========================================
@dataclass
class ScrapeRecord:
    """Record of a single scrape operation."""
    id: str  # Unique ID (timestamp-based)
    timestamp: str  # When scrape was performed
    mode: str  # "username", "keywords", "batch", "links"
    target: str  # Username, keywords, or "batch (5 users)"
    tweet_count: int
    date_range: str  # "2024-01-01 to 2024-12-31"
    method: str  # "cookie" or API name
    cost: float  # Estimated cost (0 for cookie)
    output_file: str  # Path to saved file
    duration_seconds: int  # How long it took
    status: str  # "completed", "stopped", "error"


class HistoryManager:
    """Manage scrape history."""
    
    MAX_RECORDS = 100  # Keep last 100 scrapes
    
    def __init__(self):
        self.records: List[ScrapeRecord] = []
        self.load()
    
    def load(self):
        """Load history from file."""
        path = get_history_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.records = [ScrapeRecord(**r) for r in data]
            except Exception:
                self.records = []
    
    def save(self):
        """Save history to file."""
        path = get_history_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump([asdict(r) for r in self.records], f, indent=2)
        except Exception:
            pass
    
    def add(self, record: ScrapeRecord):
        """Add a new record."""
        self.records.insert(0, record)
        # Trim to max size
        self.records = self.records[:self.MAX_RECORDS]
        self.save()
    
    def create_record(
        self,
        mode: str,
        target: str,
        tweet_count: int,
        start_date: str,
        end_date: str,
        method: str,
        cost: float,
        output_file: str,
        duration_seconds: int,
        status: str = "completed",
    ) -> ScrapeRecord:
        """Create and add a new record."""
        record = ScrapeRecord(
            id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            mode=mode,
            target=target,
            tweet_count=tweet_count,
            date_range=f"{start_date} to {end_date}",
            method=method,
            cost=cost,
            output_file=output_file,
            duration_seconds=duration_seconds,
            status=status,
        )
        self.add(record)
        return record
    
    def get_recent(self, count: int = 20) -> List[ScrapeRecord]:
        """Get most recent records."""
        return self.records[:count]
    
    def get_total_stats(self) -> Dict:
        """Get overall statistics."""
        if not self.records:
            return {
                "total_scrapes": 0,
                "total_tweets": 0,
                "total_cost": 0.0,
            }
        
        return {
            "total_scrapes": len(self.records),
            "total_tweets": sum(r.tweet_count for r in self.records),
            "total_cost": sum(r.cost for r in self.records),
        }
    
    def clear(self):
        """Clear all history."""
        self.records = []
        self.save()


# ========================================
# COST ESTIMATION
# ========================================
API_COSTS = {
    "cookie": 0.0,
    "tweetx": 0.00014,  # $0.14 per 1000 = $0.00014 per tweet
    "twitterapi_io": 0.00015,
    "official_x": 0.0,  # Subscription-based
}


def estimate_cost(method: str, estimated_tweets: int) -> float:
    """Estimate cost for a scrape operation."""
    cost_per_tweet = API_COSTS.get(method, 0.0)
    return cost_per_tweet * estimated_tweets


def format_cost(cost: float) -> str:
    """Format cost as string."""
    if cost == 0:
        return "Free"
    elif cost < 0.01:
        return f"${cost:.4f}"
    else:
        return f"${cost:.2f}"


def estimate_tweets_in_range(days: int, tweets_per_day: int = 10) -> int:
    """Rough estimate of tweets in a date range."""
    # Default assumption: average user posts ~10 tweets/day
    # This is very rough - actual varies wildly
    return days * tweets_per_day


# ========================================
# DATE RANGE PRESETS
# ========================================
def get_date_presets() -> List[tuple]:
    """Get preset date ranges."""
    today = datetime.now()
    
    return [
        ("Last 7 days", 
         (today - timedelta(days=7)).strftime("%Y-%m-%d"),
         today.strftime("%Y-%m-%d")),
        
        ("Last 30 days",
         (today - timedelta(days=30)).strftime("%Y-%m-%d"),
         today.strftime("%Y-%m-%d")),
        
        ("Last 90 days",
         (today - timedelta(days=90)).strftime("%Y-%m-%d"),
         today.strftime("%Y-%m-%d")),
        
        ("This month",
         today.replace(day=1).strftime("%Y-%m-%d"),
         today.strftime("%Y-%m-%d")),
        
        ("Last month",
         (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d"),
         (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")),
        
        ("This year",
         today.replace(month=1, day=1).strftime("%Y-%m-%d"),
         today.strftime("%Y-%m-%d")),
        
        ("Last year",
         (today.replace(month=1, day=1) - timedelta(days=1)).replace(month=1, day=1).strftime("%Y-%m-%d"),
         (today.replace(month=1, day=1) - timedelta(days=1)).strftime("%Y-%m-%d")),
    ]


# ========================================
# FILTERS
# ========================================
@dataclass
class TweetFilters:
    """Filter settings for tweets."""
    min_likes: int = 0
    min_retweets: int = 0
    min_replies: int = 0
    exclude_retweets: bool = False
    exclude_replies: bool = True
    media_only: bool = False
    verified_only: bool = False
    
    def apply(self, tweets: List[Dict]) -> List[Dict]:
        """Apply filters to a list of tweets."""
        filtered = []
        
        for tweet in tweets:
            # Get values with safe defaults
            likes = tweet.get('likes', 0) or tweet.get('like_count', 0) or 0
            retweets = tweet.get('retweets', 0) or tweet.get('retweet_count', 0) or 0
            replies = tweet.get('replies', 0) or tweet.get('reply_count', 0) or 0
            text = tweet.get('text', '') or tweet.get('full_text', '') or ''
            
            # Apply filters
            if likes < self.min_likes:
                continue
            if retweets < self.min_retweets:
                continue
            if replies < self.min_replies:
                continue
            
            # Check if retweet
            if self.exclude_retweets:
                if text.startswith('RT @') or tweet.get('is_retweet'):
                    continue
            
            # Check if reply
            if self.exclude_replies:
                if text.startswith('@') or tweet.get('in_reply_to_status_id'):
                    continue
            
            # Media only
            if self.media_only:
                has_media = (
                    tweet.get('media') or 
                    tweet.get('has_media') or
                    tweet.get('entities', {}).get('media')
                )
                if not has_media:
                    continue
            
            filtered.append(tweet)
        
        return filtered
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "TweetFilters":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


# ========================================
# ANALYTICS
# ========================================
@dataclass
class ScrapeAnalytics:
    """Analytics for a completed scrape."""
    total_tweets: int = 0
    unique_users: int = 0
    date_range_days: int = 0
    
    # Engagement stats
    total_likes: int = 0
    total_retweets: int = 0
    total_replies: int = 0
    total_views: int = 0
    
    avg_likes: float = 0.0
    avg_retweets: float = 0.0
    avg_replies: float = 0.0
    
    max_likes: int = 0
    max_retweets: int = 0
    
    # Top tweet
    top_tweet_text: str = ""
    top_tweet_likes: int = 0
    top_tweet_url: str = ""
    
    # Activity patterns
    most_active_day: str = ""  # "Monday"
    most_active_hour: int = -1  # 0-23
    tweets_per_day: float = 0.0
    
    # Content stats
    avg_tweet_length: float = 0.0
    tweets_with_media: int = 0
    tweets_with_links: int = 0
    retweet_count: int = 0
    reply_count: int = 0


def calculate_analytics(tweets: List[Dict]) -> ScrapeAnalytics:
    """Calculate analytics from a list of tweets."""
    if not tweets:
        return ScrapeAnalytics()
    
    analytics = ScrapeAnalytics()
    analytics.total_tweets = len(tweets)
    
    # Collect data
    users = set()
    dates = []
    day_counts = Counter()
    hour_counts = Counter()
    
    total_length = 0
    
    for tweet in tweets:
        # User
        username = tweet.get('username') or tweet.get('user', {}).get('screen_name', '')
        if username:
            users.add(username)
        
        # Engagement
        likes = int(tweet.get('likes', 0) or tweet.get('like_count', 0) or 0)
        retweets = int(tweet.get('retweets', 0) or tweet.get('retweet_count', 0) or 0)
        replies = int(tweet.get('replies', 0) or tweet.get('reply_count', 0) or 0)
        views = int(tweet.get('views', 0) or tweet.get('view_count', 0) or 0)
        
        analytics.total_likes += likes
        analytics.total_retweets += retweets
        analytics.total_replies += replies
        analytics.total_views += views
        
        # Track max
        if likes > analytics.max_likes:
            analytics.max_likes = likes
            analytics.top_tweet_text = (tweet.get('text', '') or '')[:100]
            analytics.top_tweet_likes = likes
            analytics.top_tweet_url = tweet.get('tweet_url', '') or tweet.get('url', '')
        
        if retweets > analytics.max_retweets:
            analytics.max_retweets = retweets
        
        # Date parsing
        date_str = tweet.get('date') or tweet.get('created_at', '')
        if date_str:
            try:
                # Try multiple formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%a %b %d %H:%M:%S +0000 %Y']:
                    try:
                        dt = datetime.strptime(date_str.replace('+0000 ', ''), fmt.replace('+0000 ', ''))
                        dates.append(dt)
                        day_counts[dt.strftime('%A')] += 1
                        hour_counts[dt.hour] += 1
                        break
                    except:
                        continue
            except:
                pass
        
        # Text analysis
        text = tweet.get('text', '') or tweet.get('full_text', '') or ''
        total_length += len(text)
        
        # Content type
        if text.startswith('RT @'):
            analytics.retweet_count += 1
        if text.startswith('@'):
            analytics.reply_count += 1
        if tweet.get('media') or 'pic.twitter.com' in text or 'photo' in str(tweet.get('entities', {})):
            analytics.tweets_with_media += 1
        if 'http' in text:
            analytics.tweets_with_links += 1
    
    # Calculate averages
    n = analytics.total_tweets
    analytics.unique_users = len(users)
    analytics.avg_likes = analytics.total_likes / n if n else 0
    analytics.avg_retweets = analytics.total_retweets / n if n else 0
    analytics.avg_replies = analytics.total_replies / n if n else 0
    analytics.avg_tweet_length = total_length / n if n else 0
    
    # Date range
    if dates:
        min_date = min(dates)
        max_date = max(dates)
        analytics.date_range_days = (max_date - min_date).days + 1
        analytics.tweets_per_day = n / analytics.date_range_days if analytics.date_range_days else 0
    
    # Most active day/hour
    if day_counts:
        analytics.most_active_day = day_counts.most_common(1)[0][0]
    if hour_counts:
        analytics.most_active_hour = hour_counts.most_common(1)[0][0]
    
    return analytics


def format_analytics_summary(analytics: ScrapeAnalytics) -> str:
    """Format analytics as a readable summary."""
    lines = [
        f"📊 SCRAPE SUMMARY",
        f"{'─' * 40}",
        f"",
        f"📝 Total tweets: {analytics.total_tweets:,}",
        f"👥 Unique users: {analytics.unique_users:,}",
        f"📅 Date span: {analytics.date_range_days} days",
        f"📈 Tweets/day: {analytics.tweets_per_day:.1f}",
        f"",
        f"💗 ENGAGEMENT",
        f"{'─' * 40}",
        f"Total likes: {analytics.total_likes:,}",
        f"Total retweets: {analytics.total_retweets:,}",
        f"Total replies: {analytics.total_replies:,}",
        f"Avg likes/tweet: {analytics.avg_likes:.1f}",
        f"Avg retweets/tweet: {analytics.avg_retweets:.1f}",
        f"",
        f"🏆 TOP TWEET ({analytics.top_tweet_likes:,} likes)",
        f"{'─' * 40}",
        f"{analytics.top_tweet_text[:80]}{'...' if len(analytics.top_tweet_text) > 80 else ''}",
        f"",
        f"📅 ACTIVITY PATTERNS",
        f"{'─' * 40}",
        f"Most active day: {analytics.most_active_day or 'N/A'}",
        f"Most active hour: {analytics.most_active_hour}:00" if analytics.most_active_hour >= 0 else "Most active hour: N/A",
        f"",
        f"📎 CONTENT BREAKDOWN",
        f"{'─' * 40}",
        f"With media: {analytics.tweets_with_media:,} ({100*analytics.tweets_with_media/analytics.total_tweets:.1f}%)" if analytics.total_tweets else "With media: 0",
        f"With links: {analytics.tweets_with_links:,}",
        f"Retweets: {analytics.retweet_count:,}",
        f"Replies: {analytics.reply_count:,}",
        f"Avg length: {analytics.avg_tweet_length:.0f} chars",
    ]
    
    return "\n".join(lines)


# ========================================
# QUEUE MANAGEMENT
# ========================================
@dataclass
class QueueItem:
    """Item in the scrape queue."""
    id: str
    username: str
    status: str = "pending"  # "pending", "running", "completed", "error", "skipped"
    tweet_count: int = 0
    error_message: str = ""


class ScrapeQueue:
    """Manage a queue of usernames to scrape."""
    
    def __init__(self):
        self.items: List[QueueItem] = []
        self._current_index = 0
    
    def add(self, username: str) -> QueueItem:
        """Add a username to the queue."""
        # Check for duplicates
        for item in self.items:
            if item.username.lower() == username.lower():
                return item
        
        item = QueueItem(
            id=f"{len(self.items)}_{username}",
            username=username,
        )
        self.items.append(item)
        return item
    
    def add_multiple(self, usernames: List[str]):
        """Add multiple usernames."""
        for username in usernames:
            username = username.strip()
            if username:
                self.add(username)
    
    def remove(self, username: str):
        """Remove a username from the queue."""
        self.items = [i for i in self.items if i.username.lower() != username.lower()]
    
    def clear(self):
        """Clear the queue."""
        self.items = []
        self._current_index = 0
    
    def get_next(self) -> Optional[QueueItem]:
        """Get next pending item."""
        for item in self.items:
            if item.status == "pending":
                return item
        return None
    
    def mark_running(self, username: str):
        """Mark an item as running."""
        for item in self.items:
            if item.username.lower() == username.lower():
                item.status = "running"
                break
    
    def mark_completed(self, username: str, tweet_count: int):
        """Mark an item as completed."""
        for item in self.items:
            if item.username.lower() == username.lower():
                item.status = "completed"
                item.tweet_count = tweet_count
                break
    
    def mark_error(self, username: str, error: str):
        """Mark an item as error."""
        for item in self.items:
            if item.username.lower() == username.lower():
                item.status = "error"
                item.error_message = error
                break
    
    def get_progress(self) -> tuple:
        """Get progress as (completed, total)."""
        completed = sum(1 for i in self.items if i.status in ("completed", "error", "skipped"))
        return completed, len(self.items)
    
    def get_total_tweets(self) -> int:
        """Get total tweets scraped."""
        return sum(i.tweet_count for i in self.items)
    
    def is_empty(self) -> bool:
        return len(self.items) == 0
    
    def has_pending(self) -> bool:
        return any(i.status == "pending" for i in self.items)


# ========================================
# EXPORT FORMATS
# ========================================
class ExportFormat:
    """Supported export formats."""
    EXCEL = "Excel (.xlsx)"
    CSV = "CSV (.csv)"
    JSON = "JSON (.json)"
    SQLITE = "SQLite (.db)"
    HTML = "HTML (.html)"
    MARKDOWN = "Markdown (.md)"
    PARQUET = "Parquet (.parquet)"
    
    @classmethod
    def all_formats(cls) -> List[str]:
        return [cls.EXCEL, cls.CSV, cls.JSON, cls.SQLITE, cls.HTML, cls.MARKDOWN, cls.PARQUET]
    
    @classmethod
    def get_extension(cls, format_name: str) -> str:
        extensions = {
            cls.EXCEL: ".xlsx",
            cls.CSV: ".csv",
            cls.JSON: ".json",
            cls.SQLITE: ".db",
            cls.HTML: ".html",
            cls.MARKDOWN: ".md",
            cls.PARQUET: ".parquet",
        }
        return extensions.get(format_name, ".xlsx")


def export_tweets(tweets: List[Dict], filepath: str, format_name: str) -> bool:
    """
    Export tweets to specified format.
    
    Args:
        tweets: List of tweet dictionaries
        filepath: Output file path
        format_name: One of ExportFormat values
    
    Returns:
        True if successful, False otherwise
    """
    try:
        import pandas as pd
        df = pd.DataFrame(tweets)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        
        if format_name == ExportFormat.EXCEL:
            df.to_excel(filepath, index=False, engine='openpyxl')
        
        elif format_name == ExportFormat.CSV:
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
        
        elif format_name == ExportFormat.JSON:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(tweets, f, indent=2, ensure_ascii=False, default=str)
        
        elif format_name == ExportFormat.SQLITE:
            import sqlite3
            conn = sqlite3.connect(filepath)
            df.to_sql('tweets', conn, if_exists='replace', index=False)
            conn.close()
        
        elif format_name == ExportFormat.HTML:
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Scraped Tweets - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #1da1f2; }}
        table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        th {{ background: #1da1f2; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f9f9f9; }}
        .stats {{ background: white; padding: 15px; margin-bottom: 20px; border-radius: 8px; }}
    </style>
</head>
<body>
    <h1>🐦 Scraped Tweets</h1>
    <div class="stats">
        <strong>Total Tweets:</strong> {len(tweets)} | 
        <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    {df.to_html(index=False, classes='tweets-table')}
</body>
</html>"""
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
        
        elif format_name == ExportFormat.MARKDOWN:
            md_content = f"""# Scraped Tweets

**Total Tweets:** {len(tweets)}  
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

{df.to_markdown(index=False)}
"""
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)
        
        elif format_name == ExportFormat.PARQUET:
            df.to_parquet(filepath, index=False)
        
        else:
            # Default to Excel
            df.to_excel(filepath, index=False, engine='openpyxl')
        
        return True
    
    except Exception as e:
        print(f"Export error: {e}")
        return False


def generate_filename(username: str = None, keywords: str = None, tweet_count: int = 0, format_name: str = None) -> str:
    """Generate a default filename for exports."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    
    if username:
        base = f"{username}_{timestamp}_{tweet_count}tweets"
    elif keywords:
        # Sanitize keywords for filename
        safe_keywords = "".join(c if c.isalnum() else "_" for c in keywords[:30])
        base = f"search_{safe_keywords}_{timestamp}"
    else:
        base = f"tweets_{timestamp}"
    
    ext = ExportFormat.get_extension(format_name) if format_name else ".xlsx"
    return base + ext


# ========================================
# RETRY LOGIC
# ========================================
@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    initial_delay: float = 2.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    retry_on_network_error: bool = True
    retry_on_rate_limit: bool = True


def calculate_retry_delay(attempt: int, config: RetryConfig = None) -> float:
    """Calculate delay before next retry using exponential backoff."""
    if config is None:
        config = RetryConfig()
    
    delay = config.initial_delay * (config.exponential_base ** attempt)
    return min(delay, config.max_delay)


class RetryHandler:
    """Handle retries with exponential backoff."""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.current_attempt = 0
        self.total_retries = 0
    
    def should_retry(self, error: Exception) -> bool:
        """Determine if we should retry based on error type."""
        if self.current_attempt >= self.config.max_retries:
            return False
        
        error_name = type(error).__name__.lower()
        error_msg = str(error).lower()
        
        # Network errors
        if self.config.retry_on_network_error:
            network_indicators = ['network', 'connection', 'timeout', 'socket', 'refused']
            if any(ind in error_name or ind in error_msg for ind in network_indicators):
                return True
        
        # Rate limit errors
        if self.config.retry_on_rate_limit:
            rate_indicators = ['rate', 'limit', '429', 'too many']
            if any(ind in error_name or ind in error_msg for ind in rate_indicators):
                return True
        
        return False
    
    def get_delay(self) -> float:
        """Get delay for current retry attempt."""
        return calculate_retry_delay(self.current_attempt, self.config)
    
    def record_attempt(self):
        """Record a retry attempt."""
        self.current_attempt += 1
        self.total_retries += 1
    
    def reset(self):
        """Reset for new operation."""
        self.current_attempt = 0
    
    def get_status_message(self) -> str:
        """Get human-readable status message."""
        delay = self.get_delay()
        return f"Retry {self.current_attempt + 1}/{self.config.max_retries} in {delay:.1f}s..."


# ========================================
# GOOGLE SHEETS INTEGRATION
# ========================================
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def check_google_credentials() -> bool:
    """Check if Google credentials are available."""
    creds_path = os.path.join(get_data_dir(), 'google_credentials.json')
    token_path = os.path.join(get_data_dir(), 'google_token.json')
    return os.path.exists(creds_path) or os.path.exists(token_path)


def upload_to_google_sheets(tweets: List[Dict], spreadsheet_name: str = None) -> Optional[str]:
    """
    Upload tweets to Google Sheets.
    
    Returns:
        Spreadsheet URL if successful, None otherwise
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import pickle
        
        creds = None
        token_path = os.path.join(get_data_dir(), 'google_token.pickle')
        creds_path = os.path.join(get_data_dir(), 'google_credentials.json')
        
        # Load existing credentials
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, GOOGLE_SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        # Build service
        service = build('sheets', 'v4', credentials=creds)
        
        # Create spreadsheet
        if not spreadsheet_name:
            spreadsheet_name = f"Tweets_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
        
        spreadsheet = {
            'properties': {'title': spreadsheet_name},
            'sheets': [{'properties': {'title': 'Tweets'}}]
        }
        
        spreadsheet = service.spreadsheets().create(body=spreadsheet).execute()
        spreadsheet_id = spreadsheet['spreadsheetId']
        
        # Prepare data
        import pandas as pd
        df = pd.DataFrame(tweets)
        headers = df.columns.tolist()
        values = [headers] + df.values.tolist()
        
        # Write data
        body = {'values': values}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='Tweets!A1',
            valueInputOption='RAW',
            body=body
        ).execute()
        
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    
    except ImportError:
        print("Google API libraries not installed. Run: pip install google-auth-oauthlib google-api-python-client")
        return None
    except Exception as e:
        print(f"Google Sheets upload error: {e}")
        return None


# ========================================
# APP SETTINGS (Extended)
# ========================================
@dataclass 
class AppSettings:
    """Extended app settings including dark mode."""
    dark_mode: bool = False
    default_export_format: str = "Excel (.xlsx)"
    auto_retry_enabled: bool = True
    max_retries: int = 3
    show_analytics_after_scrape: bool = True
    show_preview_before_save: bool = False
    google_sheets_enabled: bool = False


def get_app_settings_path():
    return os.path.join(get_data_dir(), "app_settings.json")


def load_app_settings() -> AppSettings:
    """Load app settings from file."""
    path = get_app_settings_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                return AppSettings(**{k: v for k, v in data.items() if hasattr(AppSettings, k)})
        except:
            pass
    return AppSettings()


def save_app_settings(settings: AppSettings):
    """Save app settings to file."""
    path = get_app_settings_path()
    try:
        with open(path, 'w') as f:
            json.dump(asdict(settings), f, indent=2)
    except:
        pass
