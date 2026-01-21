"""
Configuration Module - Application settings and API key management.

This module provides:
- Secure API key storage and retrieval
- Application settings management
- Configuration file handling

Usage:
    from src.config import get_api_key, set_api_key, get_api_key_manager
    
    # Get an API key
    key = get_api_key("tweetx")
    
    # Set an API key
    set_api_key("tweetx", "your_api_key_here")
    
    # Get the manager for more control
    manager = get_api_key_manager()
    status = manager.get_all_status()
"""

from .api_keys import (
    APIKeyConfig,
    APIKeysConfig,
    APIKeyManager,
    get_api_key_manager,
    get_api_key,
    set_api_key,
    ENV_VAR_MAPPING,
)


__all__ = [
    "APIKeyConfig",
    "APIKeysConfig",
    "APIKeyManager",
    "get_api_key_manager",
    "get_api_key",
    "set_api_key",
    "ENV_VAR_MAPPING",
]
