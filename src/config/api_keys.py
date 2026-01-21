"""
API Keys Configuration - Secure loading and storage of API keys.

This module handles:
- Loading API keys from config file or environment variables
- Saving API keys to config file
- Validating API key format
- Masking API keys for display

Security Notes:
- Config file (config/api_keys.json) should be in .gitignore
- Environment variables take precedence over config file
- Keys are never logged or displayed in full
"""

import os
import json
from typing import Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict
import logging

logger = logging.getLogger(__name__)


# Environment variable names for each provider
ENV_VAR_MAPPING = {
    "tweetx": "TWEETX_API_KEY",
    "twitterapi_io": "TWITTERAPI_IO_KEY",
    "official_x": "X_BEARER_TOKEN",
}

# Default config file location (relative to project root)
DEFAULT_CONFIG_DIR = "config"
DEFAULT_CONFIG_FILE = "api_keys.json"


@dataclass
class APIKeyConfig:
    """Configuration for a single API provider."""
    api_key: str = ""
    enabled: bool = False
    # Additional provider-specific settings
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key and self.api_key.strip())
    
    def get_masked_key(self, visible_chars: int = 4) -> str:
        """Get masked version of API key for display."""
        if not self.api_key:
            return "(not configured)"
        
        key = self.api_key
        if len(key) <= visible_chars * 2:
            return "*" * len(key)
        
        return f"{key[:visible_chars]}{'*' * (len(key) - visible_chars * 2)}{key[-visible_chars:]}"


@dataclass
class APIKeysConfig:
    """Configuration for all API providers."""
    tweetx: APIKeyConfig = field(default_factory=APIKeyConfig)
    twitterapi_io: APIKeyConfig = field(default_factory=APIKeyConfig)
    official_x: APIKeyConfig = field(default_factory=APIKeyConfig)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "tweetx": asdict(self.tweetx),
            "twitterapi_io": asdict(self.twitterapi_io),
            "official_x": asdict(self.official_x),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "APIKeysConfig":
        """Create from dictionary (JSON deserialization)."""
        config = cls()
        
        if "tweetx" in data:
            config.tweetx = APIKeyConfig(**data["tweetx"])
        if "twitterapi_io" in data:
            config.twitterapi_io = APIKeyConfig(**data["twitterapi_io"])
        if "official_x" in data:
            config.official_x = APIKeyConfig(**data["official_x"])
        
        return config
    
    def get_provider_config(self, provider: str) -> APIKeyConfig:
        """Get config for a specific provider."""
        provider = provider.lower().replace("-", "_")
        return getattr(self, provider, APIKeyConfig())
    
    def set_provider_config(self, provider: str, config: APIKeyConfig) -> None:
        """Set config for a specific provider."""
        provider = provider.lower().replace("-", "_")
        if hasattr(self, provider):
            setattr(self, provider, config)


class APIKeyManager:
    """
    Manager for API key configuration.
    
    Handles loading, saving, and accessing API keys securely.
    Priority order: Environment variables > Config file
    """
    
    def __init__(self, config_dir: str = None):
        """
        Initialize API key manager.
        
        Args:
            config_dir: Directory containing config files.
                       If None, uses project default.
        """
        self.config_dir = config_dir or self._find_config_dir()
        self.config_file = os.path.join(self.config_dir, DEFAULT_CONFIG_FILE)
        self._config: Optional[APIKeysConfig] = None
    
    def _find_config_dir(self) -> str:
        """Find the config directory."""
        # Try relative to this file
        this_dir = Path(__file__).parent.parent.parent  # src/config -> src -> project root
        config_dir = this_dir / DEFAULT_CONFIG_DIR
        
        if config_dir.exists():
            return str(config_dir)
        
        # Try current working directory
        cwd_config = Path.cwd() / DEFAULT_CONFIG_DIR
        if cwd_config.exists():
            return str(cwd_config)
        
        # Create default location
        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir)
    
    def load(self) -> APIKeysConfig:
        """
        Load API key configuration.
        
        Priority:
        1. Environment variables
        2. Config file
        
        Returns:
            APIKeysConfig object
        """
        # Start with config file
        config = self._load_from_file()
        
        # Override with environment variables
        config = self._apply_env_vars(config)
        
        self._config = config
        return config
    
    def save(self, config: APIKeysConfig = None) -> bool:
        """
        Save API key configuration to file.
        
        Args:
            config: Configuration to save. If None, saves current config.
        
        Returns:
            True if successful, False otherwise.
        """
        config = config or self._config
        if not config:
            logger.warning("No configuration to save")
            return False
        
        try:
            # Ensure directory exists
            os.makedirs(self.config_dir, exist_ok=True)
            
            # Save to file
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
            
            logger.info(f"API keys saved to {self.config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save API keys: {e}")
            return False
    
    def get_key(self, provider: str) -> Optional[str]:
        """
        Get API key for a provider.
        
        Args:
            provider: Provider name (e.g., "tweetx")
        
        Returns:
            API key string or None if not configured
        """
        if not self._config:
            self.load()
        
        # Check environment variable first
        env_var = ENV_VAR_MAPPING.get(provider.lower())
        if env_var:
            env_key = os.environ.get(env_var)
            if env_key:
                return env_key
        
        # Fall back to config file
        config = self._config.get_provider_config(provider)
        if config.is_configured():
            return config.api_key
        
        return None
    
    def set_key(self, provider: str, api_key: str, enabled: bool = True) -> bool:
        """
        Set API key for a provider.
        
        Args:
            provider: Provider name
            api_key: The API key
            enabled: Whether to enable this provider
        
        Returns:
            True if successful
        """
        if not self._config:
            self.load()
        
        config = APIKeyConfig(api_key=api_key, enabled=enabled)
        self._config.set_provider_config(provider, config)
        
        return self.save()
    
    def remove_key(self, provider: str) -> bool:
        """
        Remove API key for a provider.
        
        Args:
            provider: Provider name
        
        Returns:
            True if successful
        """
        return self.set_key(provider, "", enabled=False)
    
    def is_configured(self, provider: str) -> bool:
        """
        Check if a provider has an API key configured.
        
        Args:
            provider: Provider name
        
        Returns:
            True if configured
        """
        return bool(self.get_key(provider))
    
    def get_masked_key(self, provider: str) -> str:
        """
        Get masked API key for display.
        
        Args:
            provider: Provider name
        
        Returns:
            Masked key string
        """
        key = self.get_key(provider)
        if not key:
            return "(not configured)"
        
        if len(key) <= 8:
            return "*" * len(key)
        
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"
    
    def get_all_status(self) -> Dict[str, Dict]:
        """
        Get configuration status for all providers.
        
        Returns:
            Dictionary with status for each provider
        """
        if not self._config:
            self.load()
        
        return {
            "tweetx": {
                "configured": self.is_configured("tweetx"),
                "masked_key": self.get_masked_key("tweetx"),
                "enabled": self._config.tweetx.enabled,
            },
            "twitterapi_io": {
                "configured": self.is_configured("twitterapi_io"),
                "masked_key": self.get_masked_key("twitterapi_io"),
                "enabled": self._config.twitterapi_io.enabled,
            },
            "official_x": {
                "configured": self.is_configured("official_x"),
                "masked_key": self.get_masked_key("official_x"),
                "enabled": self._config.official_x.enabled,
            },
        }
    
    def _load_from_file(self) -> APIKeysConfig:
        """Load configuration from JSON file."""
        if not os.path.exists(self.config_file):
            logger.info(f"Config file not found: {self.config_file}")
            return APIKeysConfig()
        
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return APIKeysConfig.from_dict(data)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return APIKeysConfig()
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            return APIKeysConfig()
    
    def _apply_env_vars(self, config: APIKeysConfig) -> APIKeysConfig:
        """Apply environment variable overrides."""
        for provider, env_var in ENV_VAR_MAPPING.items():
            env_key = os.environ.get(env_var)
            if env_key:
                logger.debug(f"Using environment variable for {provider}")
                provider_config = APIKeyConfig(api_key=env_key, enabled=True)
                config.set_provider_config(provider, provider_config)
        
        return config


# Global instance for convenience
_manager: Optional[APIKeyManager] = None


def get_api_key_manager(config_dir: str = None) -> APIKeyManager:
    """
    Get the global API key manager instance.
    
    Args:
        config_dir: Optional config directory override
    
    Returns:
        APIKeyManager instance
    """
    global _manager
    
    if _manager is None or config_dir:
        _manager = APIKeyManager(config_dir)
    
    return _manager


def get_api_key(provider: str) -> Optional[str]:
    """
    Convenience function to get an API key.
    
    Args:
        provider: Provider name
    
    Returns:
        API key or None
    """
    return get_api_key_manager().get_key(provider)


def set_api_key(provider: str, api_key: str, enabled: bool = True) -> bool:
    """
    Convenience function to set an API key.
    
    Args:
        provider: Provider name
        api_key: The API key
        enabled: Whether to enable
    
    Returns:
        True if successful
    """
    return get_api_key_manager().set_key(provider, api_key, enabled)
