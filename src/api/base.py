"""
Base API Scraper - Abstract base class for all Twitter/X API providers.

All API scrapers must inherit from this class and implement the required methods.
This ensures consistent interface across different API providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from datetime import datetime
from enum import Enum


class APIProviderType(Enum):
    """Supported API provider types."""
    TWEETX = "tweetx"
    TWITTERAPI_IO = "twitterapi_io"
    OFFICIAL_X = "official_x"


class APIPricingType(Enum):
    """Pricing model types."""
    PAY_AS_YOU_GO = "pay_as_you_go"
    MONTHLY = "monthly"
    FREE_TIER = "free_tier"


@dataclass
class APIPricing:
    """Pricing information for an API provider."""
    pricing_type: APIPricingType
    cost_per_1000_tweets: float = 0.0  # For pay-as-you-go
    monthly_cost: float = 0.0  # For monthly plans
    free_tier_limit: int = 0  # Monthly free tweets
    currency: str = "USD"
    
    def estimate_cost(self, tweet_count: int) -> float:
        """Estimate cost for a given number of tweets."""
        if self.pricing_type == APIPricingType.FREE_TIER:
            return 0.0
        elif self.pricing_type == APIPricingType.PAY_AS_YOU_GO:
            return (tweet_count / 1000) * self.cost_per_1000_tweets
        else:
            return self.monthly_cost
    
    def format_cost(self, tweet_count: int) -> str:
        """Format cost as human-readable string."""
        cost = self.estimate_cost(tweet_count)
        if cost == 0:
            return "Free"
        return f"${cost:.4f} {self.currency}"


@dataclass
class ScrapedTweet:
    """
    Unified tweet data structure.
    All API scrapers must return data in this format.
    """
    tweet_id: str
    date: str  # Format: YYYY-MM-DD HH:MM:SS
    username: str
    display_name: str
    text: str
    retweets: int = 0
    likes: int = 0
    replies: int = 0
    quotes: int = 0
    views: int = 0
    tweet_url: str = ""
    source_api: str = ""  # Which API provided this data
    raw_data: Dict = field(default_factory=dict)  # Original API response
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for CSV/Excel export."""
        return {
            "date": self.date,
            "username": self.username,
            "display_name": self.display_name,
            "text": self.text,
            "retweets": self.retweets,
            "likes": self.likes,
            "replies": self.replies,
            "quotes": self.quotes,
            "views": self.views,
            "tweet_id": self.tweet_id,
            "tweet_url": self.tweet_url,
        }
    
    def to_row(self) -> List:
        """Convert to list for CSV/Excel row."""
        return [
            self.date,
            self.username,
            self.display_name,
            self.text,
            self.retweets,
            self.likes,
            self.replies,
            self.quotes,
            self.views,
            self.tweet_id,
            self.tweet_url,
        ]


@dataclass
class APISearchResult:
    """Result of an API search operation."""
    tweets: List[ScrapedTweet]
    total_found: int
    api_calls_made: int
    estimated_cost: float
    has_more: bool = False
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.error is None


class APIError(Exception):
    """Base exception for API errors."""
    pass


class APIAuthenticationError(APIError):
    """API key invalid or expired."""
    pass


class APIRateLimitError(APIError):
    """Rate limit exceeded."""
    def __init__(self, message: str, retry_after: int = 900):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds to wait


class APIQuotaExceededError(APIError):
    """Monthly quota exceeded."""
    pass


class APINetworkError(APIError):
    """Network-related error."""
    pass


class BaseAPIScraper(ABC):
    """
    Abstract base class for all Twitter/X API scrapers.
    
    Each API provider implementation must:
    1. Inherit from this class
    2. Implement all abstract methods
    3. Set the class attributes (name, provider_type, pricing)
    """
    
    # Class attributes - must be set by subclasses
    name: str = "Unknown API"
    provider_type: APIProviderType = None
    pricing: APIPricing = None
    requires_auth: bool = True
    
    def __init__(self, api_key: str = None, **kwargs):
        """
        Initialize the API scraper.
        
        Args:
            api_key: The API key/token for authentication
            **kwargs: Additional provider-specific options
        """
        self.api_key = api_key
        self._is_authenticated = False
        self._total_tweets_fetched = 0
        self._total_api_calls = 0
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Validate API key and authenticate with the service.
        
        Returns:
            True if authentication successful, False otherwise.
        
        Raises:
            APIAuthenticationError: If authentication fails.
        """
        pass
    
    @abstractmethod
    def search_tweets(
        self,
        query: str = None,
        username: str = None,
        keywords: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        max_results: int = 100,
        use_and: bool = False,
        exclude_replies: bool = True,
        progress_callback: Callable[[str], None] = None,
        should_stop_callback: Callable[[], bool] = None,
    ) -> APISearchResult:
        """
        Search for tweets based on criteria.
        
        Args:
            query: Raw search query string (if provided, overrides other params)
            username: Twitter username to search (without @)
            keywords: List of keywords to search
            start_date: Start date (YYYY-MM-DD or YYYY-MM-DD_HH:MM:SS)
            end_date: End date (YYYY-MM-DD or YYYY-MM-DD_HH:MM:SS)
            max_results: Maximum tweets to return
            use_and: If True, ALL keywords must match; if False, ANY keyword
            exclude_replies: If True, filter out reply tweets
            progress_callback: Function to report progress messages
            should_stop_callback: Function that returns True to stop scraping
        
        Returns:
            APISearchResult containing tweets and metadata.
        
        Raises:
            APIAuthenticationError: If not authenticated
            APIRateLimitError: If rate limit exceeded
            APIQuotaExceededError: If quota exceeded
            APINetworkError: If network error occurs
        """
        pass
    
    @abstractmethod
    def get_user_tweets(
        self,
        username: str,
        start_date: str = None,
        end_date: str = None,
        max_results: int = 100,
        exclude_replies: bool = True,
        progress_callback: Callable[[str], None] = None,
        should_stop_callback: Callable[[], bool] = None,
    ) -> APISearchResult:
        """
        Get tweets from a specific user's timeline.
        
        Args:
            username: Twitter username (without @)
            start_date: Start date filter
            end_date: End date filter
            max_results: Maximum tweets to return
            exclude_replies: If True, filter out reply tweets
            progress_callback: Function to report progress
            should_stop_callback: Function that returns True to stop
        
        Returns:
            APISearchResult containing tweets and metadata.
        """
        pass
    
    @abstractmethod
    def get_tweet_by_id(self, tweet_id: str) -> Optional[ScrapedTweet]:
        """
        Get a single tweet by its ID.
        
        Args:
            tweet_id: The tweet ID
        
        Returns:
            ScrapedTweet if found, None otherwise.
        """
        pass
    
    def test_connection(self) -> bool:
        """
        Test if the API connection is working.
        
        Returns:
            True if connection successful, False otherwise.
        """
        try:
            return self.authenticate()
        except Exception:
            return False
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics for this session.
        
        Returns:
            Dictionary with usage stats.
        """
        return {
            "provider": self.name,
            "total_tweets_fetched": self._total_tweets_fetched,
            "total_api_calls": self._total_api_calls,
            "estimated_cost": self.pricing.estimate_cost(self._total_tweets_fetched) if self.pricing else 0,
        }
    
    def reset_stats(self):
        """Reset usage statistics."""
        self._total_tweets_fetched = 0
        self._total_api_calls = 0
    
    # ========================================
    # HELPER METHODS (can be overridden)
    # ========================================
    
    def _build_search_query(
        self,
        username: str = None,
        keywords: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        use_and: bool = False,
        exclude_replies: bool = True,
    ) -> str:
        """
        Build a search query string from parameters.
        Default implementation - can be overridden for provider-specific syntax.
        
        Args:
            username: Twitter username
            keywords: List of keywords
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            use_and: Use AND logic for keywords
            exclude_replies: Exclude reply tweets
        
        Returns:
            Search query string.
        """
        parts = []
        
        if username:
            parts.append(f"from:{username.lstrip('@')}")
        
        if keywords:
            if use_and:
                parts.extend(keywords)
            else:
                keyword_part = " OR ".join(keywords)
                if len(keywords) > 1:
                    parts.append(f"({keyword_part})")
                else:
                    parts.append(keyword_part)
        
        if start_date:
            # Handle both YYYY-MM-DD and YYYY-MM-DD_HH:MM:SS formats
            date_only = start_date.split("_")[0]
            parts.append(f"since:{date_only}")
        
        if end_date:
            date_only = end_date.split("_")[0]
            parts.append(f"until:{date_only}")
        
        if exclude_replies:
            parts.append("-filter:replies")
        
        return " ".join(parts)
    
    def _parse_date(self, date_string: str) -> Optional[datetime]:
        """
        Parse various date formats to datetime object.
        
        Args:
            date_string: Date string in various formats
        
        Returns:
            datetime object or None if parsing fails.
        """
        if not date_string:
            return None
        
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d_%H:%M:%S",
            "%Y-%m-%d",
            "%a %b %d %H:%M:%S %z %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_string.replace("+0000", "").strip(), fmt.replace("%z", ""))
            except ValueError:
                continue
        
        return None
    
    def _format_date(self, dt: datetime) -> str:
        """
        Format datetime to standard string format.
        
        Args:
            dt: datetime object
        
        Returns:
            Formatted date string (YYYY-MM-DD HH:MM:SS)
        """
        if dt is None:
            return "N/A"
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def _is_within_date_range(
        self,
        tweet_date: str,
        start_date: str = None,
        end_date: str = None,
    ) -> bool:
        """
        Check if a tweet date is within the specified range.
        
        Args:
            tweet_date: Tweet date string
            start_date: Start date filter
            end_date: End date filter
        
        Returns:
            True if within range, False otherwise.
        """
        if not start_date and not end_date:
            return True
        
        tweet_dt = self._parse_date(tweet_date)
        if not tweet_dt:
            return True  # Can't filter, include it
        
        if start_date:
            start_dt = self._parse_date(start_date)
            if start_dt and tweet_dt < start_dt:
                return False
        
        if end_date:
            end_dt = self._parse_date(end_date)
            if end_dt and tweet_dt > end_dt:
                return False
        
        return True
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', authenticated={self._is_authenticated})>"
