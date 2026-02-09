"""
Configuration Manager - Handles loading and accessing configuration
"""
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
            return config or {}
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration: {e}")
            return {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'user.email')"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def get_user_profile(self) -> Dict[str, Any]:
        """Get user profile configuration"""
        return self._config.get('user', {})
    
    def get_search_keywords(self) -> Dict[str, List[str]]:
        """Get search keywords configuration"""
        return self._config.get('search', {}).get('keywords', {})
    
    def get_platform_config(self, platform: str) -> Dict[str, Any]:
        """Get configuration for a specific platform"""
        return self._config.get('platforms', {}).get(platform, {})
    
    def get_enabled_platforms(self) -> List[str]:
        """Get list of enabled platforms"""
        platforms = self._config.get('platforms', {})
        return [name for name, config in platforms.items() if config.get('enabled', False)]
    
    def get_anti_detection_config(self) -> Dict[str, Any]:
        """Get anti-detection configuration"""
        return self._config.get('anti_detection', {})
    
    def get_application_config(self) -> Dict[str, Any]:
        """Get application settings"""
        return self._config.get('application', {})
    
    def get_database_path(self) -> str:
        """Get database file path"""
        return self._config.get('database', {}).get('path', 'database/job_application.db')
    
    def get_daily_limit(self) -> int:
        """Get daily application limit"""
        return self._config.get('application', {}).get('daily_limit', 30)
    
    def get_min_relevance_score(self) -> float:
        """Get minimum relevance score for shortlisting"""
        return self._config.get('search', {}).get('min_relevance_score', 6.0)
    
    def get_delay_range(self) -> tuple:
        """Get random delay range (min, max) in seconds"""
        anti_detect = self._config.get('anti_detection', {})
        return (anti_detect.get('delay_min', 3), anti_detect.get('delay_max', 8))
    
    def get_user_agents(self) -> List[str]:
        """Get list of user agents for rotation"""
        return [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
    
    def get_cover_letter_template_path(self, language: str = 'fr') -> str:
        """Get cover letter template path for specified language"""
        key = f'template_{language}'
        path = self._config.get('application', {}).get('cover_letter', {}).get(key)
        return path or f"documents/templates/cover_letter_{language}_template.txt"
    
    def reload(self):
        """Reload configuration from file"""
        self._config = self._load_config()

# Global config instance
_config_instance = None

def get_config(config_path: str = "config/config.yaml") -> ConfigManager:
    """Get or create global config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager(config_path)
    return _config_instance
