"""
API Scraper Registry - Factory for creating API scraper instances.

This module provides a central registry for all available API scrapers
and a factory method to create scraper instances by provider type.
"""

from typing import Dict, Type, List, Optional
from .base import (
    BaseAPIScraper,
    APIProviderType,
    APIPricing,
    APIPricingType,
    APIAuthenticationError,
)
from .tweetx_api import TweetXAPIScraper


# Registry of all available API scrapers
_SCRAPER_REGISTRY: Dict[APIProviderType, Type[BaseAPIScraper]] = {
    APIProviderType.TWEETX: TweetXAPIScraper,
    # Future scrapers will be added here:
    # APIProviderType.TWITTERAPI_IO: TwitterAPIioScraper,
    # APIProviderType.OFFICIAL_X: OfficialXAPIScraper,
}


# Provider display information
PROVIDER_INFO = {
    APIProviderType.TWEETX: {
        "name": "TweetX",
        "description": "TwexAPI.io - Pay-as-you-go Twitter data access",
        "pricing_display": "$0.14/1k",
        "pricing_type": "Pay-as-you-go",
        "website": "https://twexapi.io",
        "signup_url": "https://twexapi.io",
        "auth_type": "API Key (Bearer Token)",
        "features": ["Search tweets", "User timeline", "Date filtering", "Pagination"],
    },
    APIProviderType.TWITTERAPI_IO: {
        "name": "TwitterAPI.io",
        "description": "Enterprise-grade Twitter data API",
        "pricing_display": "$0.15/1k",
        "pricing_type": "Pay-as-you-go",
        "website": "https://twitterapi.io",
        "signup_url": "https://twitterapi.io/signup",
        "auth_type": "API Key",
        "features": ["Search tweets", "User timeline", "Real-time data", "High volume"],
        "available": False,  # Not yet implemented
    },
    APIProviderType.OFFICIAL_X: {
        "name": "Official X API",
        "description": "Official Twitter/X API v2",
        "pricing_display": "$100+/mo",
        "pricing_type": "Monthly subscription",
        "website": "https://developer.twitter.com",
        "signup_url": "https://developer.twitter.com/en/portal/dashboard",
        "auth_type": "Bearer Token + OAuth",
        "features": ["Full API access", "Streaming", "Premium endpoints"],
        "available": False,  # Not yet implemented
    },
}


def get_scraper(
    provider: APIProviderType,
    api_key: str = None,
    **kwargs
) -> BaseAPIScraper:
    """
    Create a scraper instance for the specified provider.
    
    Args:
        provider: The API provider type
        api_key: API key for authentication
        **kwargs: Additional provider-specific options
    
    Returns:
        Configured scraper instance
    
    Raises:
        ValueError: If provider is not supported
        APIAuthenticationError: If API key is required but not provided
    """
    if provider not in _SCRAPER_REGISTRY:
        available = ", ".join(p.value for p in _SCRAPER_REGISTRY.keys())
        raise ValueError(
            f"Unknown provider: {provider}. Available providers: {available}"
        )
    
    scraper_class = _SCRAPER_REGISTRY[provider]
    
    if scraper_class.requires_auth and not api_key:
        raise APIAuthenticationError(
            f"{provider.value} requires an API key"
        )
    
    return scraper_class(api_key=api_key, **kwargs)


def get_available_providers() -> List[APIProviderType]:
    """
    Get list of all available (implemented) API providers.
    
    Returns:
        List of available provider types
    """
    return list(_SCRAPER_REGISTRY.keys())


def get_all_providers() -> List[APIProviderType]:
    """
    Get list of all provider types (including not yet implemented).
    
    Returns:
        List of all provider types
    """
    return list(APIProviderType)


def get_provider_info(provider: APIProviderType) -> dict:
    """
    Get display information for a provider.
    
    Args:
        provider: The provider type
    
    Returns:
        Dictionary with provider information
    """
    return PROVIDER_INFO.get(provider, {
        "name": provider.value,
        "description": "Unknown provider",
        "available": False,
    })


def is_provider_available(provider: APIProviderType) -> bool:
    """
    Check if a provider is implemented and available.
    
    Args:
        provider: The provider type
    
    Returns:
        True if provider is available
    """
    return provider in _SCRAPER_REGISTRY


def register_scraper(
    provider: APIProviderType,
    scraper_class: Type[BaseAPIScraper]
) -> None:
    """
    Register a new scraper class for a provider.
    
    This allows for dynamic registration of new API scrapers.
    
    Args:
        provider: The provider type
        scraper_class: The scraper class (must inherit from BaseAPIScraper)
    
    Raises:
        TypeError: If scraper_class is not a subclass of BaseAPIScraper
    """
    if not issubclass(scraper_class, BaseAPIScraper):
        raise TypeError(
            f"Scraper class must inherit from BaseAPIScraper, got {scraper_class}"
        )
    
    _SCRAPER_REGISTRY[provider] = scraper_class


def get_provider_for_dropdown() -> List[tuple]:
    """
    Get provider information formatted for GUI dropdown.
    
    Returns:
        List of tuples: (display_name, provider_type, is_available)
    """
    result = []
    
    for provider in APIProviderType:
        info = get_provider_info(provider)
        is_available = is_provider_available(provider)
        
        if is_available:
            display = f"{info['name']} ({info['pricing_display']})"
        else:
            display = f"{info['name']} (Coming Soon)"
        
        result.append((display, provider, is_available))
    
    return result


def test_api_key(provider: APIProviderType, api_key: str) -> tuple:
    """
    Test if an API key is valid for a provider.
    
    Args:
        provider: The provider type
        api_key: The API key to test
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not is_provider_available(provider):
        return False, f"{provider.value} is not yet implemented"
    
    if not api_key:
        return False, "API key is required"
    
    try:
        scraper = get_scraper(provider, api_key)
        if scraper.authenticate():
            return True, "API key is valid"
        else:
            return False, "Authentication failed"
    except APIAuthenticationError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Error: {str(e)}"
