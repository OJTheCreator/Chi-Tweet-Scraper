"""
TweetX API Scraper - Implementation for TwitterXAPI.com (api.twexapi.io)

This scraper uses the TweetX API service for Twitter/X data access.
Pricing: ~$0.14 per 1,000 tweets (pay-as-you-go)

Documentation: https://twitterxapi.com/docs
"""

import requests
import time
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta

from .base import (
    BaseAPIScraper,
    APIProviderType,
    APIPricing,
    APIPricingType,
    ScrapedTweet,
    APISearchResult,
    APIError,
    APIAuthenticationError,
    APIRateLimitError,
    APIQuotaExceededError,
    APINetworkError,
)


class TweetXAPIScraper(BaseAPIScraper):
    """
    TweetX API Scraper implementation.
    
    Uses api.twexapi.io for Twitter/X data access.
    """
    
    name = "TweetX API"
    provider_type = APIProviderType.TWEETX
    pricing = APIPricing(
        pricing_type=APIPricingType.PAY_AS_YOU_GO,
        cost_per_1000_tweets=0.14,
        currency="USD",
    )
    requires_auth = True
    
    # API Configuration
    BASE_URL = "https://api.twexapi.io"
    MAX_ITEMS_PER_REQUEST = 100
    DEFAULT_TIMEOUT = 30
    MAX_CONSECUTIVE_EMPTY = 3
    REQUEST_DELAY = 2  # Seconds between requests
    
    def __init__(self, api_key: str = None, **kwargs):
        """
        Initialize TweetX API scraper.
        
        Args:
            api_key: TweetX API key (Bearer token)
            **kwargs: Additional options
        """
        super().__init__(api_key, **kwargs)
        self.headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json",
        }
    
    def authenticate(self) -> bool:
        """
        Validate API key by making a test request.
        
        Returns:
            True if authentication successful.
        
        Raises:
            APIAuthenticationError: If authentication fails.
        """
        if not self.api_key:
            raise APIAuthenticationError("API key is required")
        
        # Make a minimal test request
        try:
            endpoint = f"{self.BASE_URL}/twitter/advanced_search"
            payload = {
                "searchTerms": ["test"],
                "maxItems": 1,
                "sortBy": "Latest",
            }
            
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
            
            if response.status_code == 200:
                self._is_authenticated = True
                return True
            elif response.status_code == 401:
                raise APIAuthenticationError("Invalid API key")
            elif response.status_code == 403:
                raise APIAuthenticationError("API key lacks required permissions")
            else:
                raise APIAuthenticationError(f"Authentication failed: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            raise APINetworkError(f"Network error during authentication: {e}")
    
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
        Search for tweets using TweetX API.
        
        Returns:
            APISearchResult with tweets and metadata.
        """
        # Build search query
        if query:
            search_query = query
        else:
            search_query = self._build_tweetx_query(
                username=username,
                keywords=keywords,
                start_date=start_date,
                end_date=end_date,
                use_and=use_and,
                exclude_replies=exclude_replies,
            )
        
        if progress_callback:
            progress_callback(f"🔍 Search query: {search_query}")
        
        all_tweets = []
        page = 1
        consecutive_empty = 0
        api_calls = 0
        
        while len(all_tweets) < max_results and consecutive_empty < self.MAX_CONSECUTIVE_EMPTY:
            # Check if stop requested
            if should_stop_callback and should_stop_callback():
                if progress_callback:
                    progress_callback("🛑 Stop requested")
                break
            
            # Calculate items for this request
            remaining = max_results - len(all_tweets)
            page_size = min(remaining, self.MAX_ITEMS_PER_REQUEST)
            
            if progress_callback:
                progress_callback(f"📄 Page {page}: Requesting {page_size} tweets...")
            
            try:
                # Make API request
                result = self._make_search_request(search_query, page_size)
                api_calls += 1
                
                if not result:
                    consecutive_empty += 1
                    if progress_callback:
                        progress_callback(f"📭 No tweets on page {page} (empty: {consecutive_empty}/{self.MAX_CONSECUTIVE_EMPTY})")
                    
                    if consecutive_empty >= self.MAX_CONSECUTIVE_EMPTY:
                        if progress_callback:
                            progress_callback("✅ All available tweets collected")
                        break
                    
                    time.sleep(self.REQUEST_DELAY)
                    page += 1
                    continue
                
                # Reset empty counter
                consecutive_empty = 0
                
                # Parse tweets
                page_tweets = self._parse_tweets(result, exclude_replies)
                
                # Filter by date range (strict filtering)
                if start_date or end_date:
                    page_tweets = self._filter_by_date(page_tweets, start_date, end_date)
                
                all_tweets.extend(page_tweets)
                
                if progress_callback:
                    cost = self.pricing.estimate_cost(len(all_tweets))
                    progress_callback(f"✓ Got {len(page_tweets)} tweets (Total: {len(all_tweets)}, Cost: ${cost:.4f})")
                
                # Check if we got fewer than requested (might be at end)
                if len(result) < page_size:
                    if progress_callback:
                        progress_callback("📋 Reached end of available results")
                    break
                
                # Delay between requests
                if len(all_tweets) < max_results:
                    time.sleep(self.REQUEST_DELAY)
                
                page += 1
                
            except APIRateLimitError as e:
                if progress_callback:
                    progress_callback(f"⏳ Rate limit hit. Waiting {e.retry_after}s...")
                time.sleep(e.retry_after)
                continue
                
            except APIAuthenticationError:
                raise
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"❌ Error: {str(e)[:50]}")
                break
        
        # Update stats
        self._total_tweets_fetched += len(all_tweets)
        self._total_api_calls += api_calls
        
        # Trim to max_results
        all_tweets = all_tweets[:max_results]
        
        if progress_callback:
            final_cost = self.pricing.estimate_cost(len(all_tweets))
            progress_callback(f"✅ Complete: {len(all_tweets)} tweets, {api_calls} API calls, ${final_cost:.4f}")
        
        return APISearchResult(
            tweets=all_tweets,
            total_found=len(all_tweets),
            api_calls_made=api_calls,
            estimated_cost=self.pricing.estimate_cost(len(all_tweets)),
            has_more=consecutive_empty < self.MAX_CONSECUTIVE_EMPTY,
        )
    
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
        Get tweets from a specific user using TweetX API.
        """
        return self.search_tweets(
            username=username,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results,
            exclude_replies=exclude_replies,
            progress_callback=progress_callback,
            should_stop_callback=should_stop_callback,
        )
    
    def get_tweet_by_id(self, tweet_id: str) -> Optional[ScrapedTweet]:
        """
        Get a single tweet by ID.
        
        Note: TweetX API may not have a direct endpoint for this.
        This is a placeholder implementation.
        """
        # TweetX may not support single tweet lookup directly
        # For now, return None
        return None
    
    # ========================================
    # PRIVATE METHODS
    # ========================================
    
    def _build_tweetx_query(
        self,
        username: str = None,
        keywords: List[str] = None,
        start_date: str = None,
        end_date: str = None,
        use_and: bool = False,
        exclude_replies: bool = True,
    ) -> str:
        """
        Build TweetX API search query.
        
        TweetX uses standard Twitter search syntax.
        """
        parts = []
        
        if username:
            parts.append(f"from:{username.lstrip('@')}")
        
        if keywords:
            if use_and:
                # All keywords must match
                parts.extend(keywords)
            else:
                # Any keyword can match
                if len(keywords) > 1:
                    parts.append(f"({' OR '.join(keywords)})")
                else:
                    parts.append(keywords[0])
        
        if start_date:
            date_only = start_date.split("_")[0]
            parts.append(f"since:{date_only}")
        
        if end_date:
            date_only = end_date.split("_")[0]
            parts.append(f"until:{date_only}")
        
        if exclude_replies:
            parts.append("-filter:replies")
        
        return " ".join(parts)
    
    def _make_search_request(self, query: str, max_items: int) -> List[Dict]:
        """
        Make a single search request to TweetX API.
        
        Returns:
            List of raw tweet data from API.
        
        Raises:
            APIAuthenticationError: If auth fails
            APIRateLimitError: If rate limited
            APINetworkError: If network error
        """
        endpoint = f"{self.BASE_URL}/twitter/advanced_search"
        
        payload = {
            "searchTerms": [query],
            "maxItems": max_items,
            "sortBy": "Latest",
        }
        
        try:
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=self.DEFAULT_TIMEOUT,
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract tweets from response
                if "data" in data and isinstance(data["data"], list):
                    return data["data"]
                elif "statuses" in data:
                    return data["statuses"]
                elif "tweets" in data:
                    return data["tweets"]
                elif isinstance(data, list):
                    return data
                else:
                    return []
                    
            elif response.status_code == 401:
                raise APIAuthenticationError("API key invalid or expired")
            elif response.status_code == 403:
                raise APIAuthenticationError("Access forbidden - check API permissions")
            elif response.status_code == 429:
                raise APIRateLimitError("Rate limit exceeded", retry_after=900)
            else:
                raise APIError(f"API error {response.status_code}: {response.text[:100]}")
                
        except requests.exceptions.Timeout:
            raise APINetworkError("Request timed out")
        except requests.exceptions.ConnectionError:
            raise APINetworkError("Connection failed")
        except requests.exceptions.RequestException as e:
            raise APINetworkError(f"Network error: {e}")
    
    def _parse_tweets(self, raw_tweets: List[Dict], exclude_replies: bool = True) -> List[ScrapedTweet]:
        """
        Parse raw API response into ScrapedTweet objects.
        """
        tweets = []
        
        for raw in raw_tweets:
            try:
                tweet = self._parse_single_tweet(raw)
                if tweet:
                    # Additional reply filtering
                    if exclude_replies and self._is_reply(raw, tweet):
                        continue
                    tweets.append(tweet)
            except Exception:
                continue
        
        return tweets
    
    def _parse_single_tweet(self, raw: Dict) -> Optional[ScrapedTweet]:
        """
        Parse a single raw tweet into ScrapedTweet.
        """
        # Extract username - try multiple fields
        username = None
        display_name = None
        
        # Method 1: Direct fields
        username = raw.get("username") or raw.get("screen_name") or raw.get("user_screen_name")
        display_name = raw.get("name") or raw.get("display_name") or raw.get("user_name")
        
        # Method 2: Nested in user object
        if "user" in raw and isinstance(raw["user"], dict):
            username = username or raw["user"].get("screen_name") or raw["user"].get("username")
            display_name = display_name or raw["user"].get("name")
        
        # Method 3: Nested in author object
        if "author" in raw and isinstance(raw["author"], dict):
            username = username or raw["author"].get("username") or raw["author"].get("screen_name")
            display_name = display_name or raw["author"].get("name")
        
        # Fallbacks
        username = username or raw.get("author_username") or raw.get("user_handle") or "N/A"
        display_name = display_name or raw.get("author_name") or raw.get("full_name") or username
        
        # Get tweet ID
        tweet_id = str(raw.get("tweet_id") or raw.get("id_str") or raw.get("id") or "")
        
        if not tweet_id:
            return None
        
        # Get text
        text = raw.get("text") or raw.get("full_text") or raw.get("content") or ""
        
        # Get metrics
        public_metrics = raw.get("public_metrics", {})
        
        retweets = int(
            raw.get("retweet_count") or 
            raw.get("retweets") or 
            public_metrics.get("retweet_count") or 0
        )
        
        replies = int(
            raw.get("reply_count") or 
            raw.get("replies") or 
            public_metrics.get("reply_count") or 0
        )
        
        likes = int(
            raw.get("like_count") or 
            raw.get("likes") or 
            raw.get("favorite_count") or 
            raw.get("favourites") or 
            public_metrics.get("like_count") or 0
        )
        
        quotes = int(
            raw.get("quote_count") or 
            raw.get("quotes") or 
            public_metrics.get("quote_count") or 0
        )
        
        views = int(
            raw.get("view_count") or 
            raw.get("views") or 
            public_metrics.get("impression_count") or 0
        )
        
        # Get date
        date_str = raw.get("created_at") or raw.get("timestamp") or raw.get("date") or ""
        parsed_date = self._parse_date(date_str)
        formatted_date = self._format_date(parsed_date) if parsed_date else date_str
        
        # Build tweet URL
        tweet_url = raw.get("url") or raw.get("tweet_url")
        if not tweet_url and username != "N/A" and tweet_id:
            tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
        
        return ScrapedTweet(
            tweet_id=tweet_id,
            date=formatted_date,
            username=username,
            display_name=display_name,
            text=text,
            retweets=retweets,
            likes=likes,
            replies=replies,
            quotes=quotes,
            views=views,
            tweet_url=tweet_url or "",
            source_api=self.name,
            raw_data=raw,
        )
    
    def _is_reply(self, raw: Dict, tweet: ScrapedTweet = None) -> bool:
        """
        Check if a tweet is a reply.
        """
        # Check text starts with @
        text = tweet.text if tweet else raw.get("text", "")
        if text.strip().startswith("@"):
            return True
        
        # Check raw data fields
        if raw.get("in_reply_to_status_id"):
            return True
        if raw.get("in_reply_to_user_id"):
            return True
        if raw.get("in_reply_to_screen_name"):
            return True
        if raw.get("is_reply"):
            return True
        
        return False
    
    def _filter_by_date(
        self,
        tweets: List[ScrapedTweet],
        start_date: str = None,
        end_date: str = None,
    ) -> List[ScrapedTweet]:
        """
        Filter tweets to only include those within date range.
        """
        if not start_date and not end_date:
            return tweets
        
        filtered = []
        
        start_dt = self._parse_date(start_date) if start_date else None
        end_dt = self._parse_date(end_date) if end_date else None
        
        # Make end_date inclusive (add one day)
        if end_dt:
            end_dt = end_dt + timedelta(days=1)
        
        for tweet in tweets:
            tweet_dt = self._parse_date(tweet.date)
            if not tweet_dt:
                continue
            
            if start_dt and tweet_dt < start_dt:
                continue
            if end_dt and tweet_dt >= end_dt:
                continue
            
            filtered.append(tweet)
        
        return filtered
