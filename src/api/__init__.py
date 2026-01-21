"""
API Scrapers Module - Twitter/X API integrations.

This module provides a unified interface for different Twitter/X API providers.
Each provider is implemented as a separate scraper class that inherits from
BaseAPIScraper, ensuring consistent interface and behavior.

Supported Providers:
- TweetX API (twitterxapi.com) - Pay-as-you-go, $0.14/1k tweets
- TwitterAPI.io (coming soon) - Pay-as-you-go, $0.15/1k tweets
- Official X API (coming soon) - Monthly subscription

Usage:
    from src.api import get_scraper, APIProviderType
    
    # Create a scraper
    scraper = get_scraper(APIProviderType.TWEETX, api_key="your_key")
    
    # Search tweets
    result = scraper.search_tweets(
        keywords=["AI", "machine learning"],
        start_date="2024-01-01",
        end_date="2024-12-31",
        max_results=1000,
    )
    
    # Access results
    for tweet in result.tweets:
        print(f"@{tweet.username}: {tweet.text}")
"""

# Base classes and types
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

# Scraper implementations
from .tweetx_api import TweetXAPIScraper

# Registry functions
from .registry import (
    get_scraper,
    get_available_providers,
    get_all_providers,
    get_provider_info,
    is_provider_available,
    register_scraper,
    get_provider_for_dropdown,
    test_api_key,
)


__all__ = [
    # Base classes
    "BaseAPIScraper",
    "APIProviderType",
    "APIPricing",
    "APIPricingType",
    "ScrapedTweet",
    "APISearchResult",
    
    # Exceptions
    "APIError",
    "APIAuthenticationError",
    "APIRateLimitError",
    "APIQuotaExceededError",
    "APINetworkError",
    
    # Scraper implementations
    "TweetXAPIScraper",
    
    # Registry functions
    "get_scraper",
    "get_available_providers",
    "get_all_providers",
    "get_provider_info",
    "is_provider_available",
    "register_scraper",
    "get_provider_for_dropdown",
    "test_api_key",
]
