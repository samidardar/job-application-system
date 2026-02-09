"""
Anti-detection utilities for web scraping and automation
Implements human-like behavior patterns to avoid bot detection
"""
import time
import random
import logging
from typing import Tuple, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class SessionConfig:
    """Configuration for a scraping session"""
    delay_min: float = 2.0
    delay_max: float = 5.0
    max_requests: int = 30
    session_break_duration: int = 300  # 5 minutes
    rotate_user_agent: bool = True

class AntiDetectionManager:
    """Manages anti-detection strategies for web scraping"""
    
    # Common user agents
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    ]
    
    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()
        self.request_count = 0
        self.session_count = 0
        self.current_user_agent = self._get_random_user_agent()
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent"""
        return random.choice(self.USER_AGENTS)
    
    def get_user_agent(self) -> str:
        """Get current user agent, rotating if enabled"""
        if self.config.rotate_user_agent:
            return self._get_random_user_agent()
        return self.current_user_agent
    
    def random_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None) -> float:
        """Apply a random delay"""
        min_delay = min_seconds or self.config.delay_min
        max_delay = max_seconds or self.config.delay_max
        
        # Add some Gaussian noise for more human-like timing
        delay = random.uniform(min_delay, max_delay)
        delay += random.gauss(0, 0.5)  # Add noise
        delay = max(min_delay, min(delay, max_delay * 1.5))  # Clamp values
        
        logger.debug(f"Sleeping for {delay:.2f} seconds")
        time.sleep(delay)
        return delay
    
    def human_like_delay(self, action_type: str = "default"):
        """Apply delays based on action type for human-like behavior"""
        delays = {
            "page_load": (3, 7),
            "scroll": (0.5, 2),
            "click": (1, 3),
            "form_fill": (2, 5),
            "submit": (5, 12),
            "default": (2, 5)
        }
        
        min_sec, max_sec = delays.get(action_type, delays["default"])
        return self.random_delay(min_sec, max_sec)
    
    def check_session_limit(self) -> bool:
        """Check if we've hit the session request limit"""
        self.request_count += 1
        
        if self.request_count >= self.config.max_requests:
            logger.info(f"Session limit reached ({self.config.max_requests} requests). Taking a break...")
            self._take_break()
            return True
        
        return False
    
    def _take_break(self):
        """Take a break between sessions"""
        break_duration = self.config.session_break_duration
        logger.info(f"Taking a {break_duration//60} minute break...")
        time.sleep(break_duration)
        
        # Reset session
        self.request_count = 0
        self.session_count += 1
        self.current_user_agent = self._get_random_user_agent()
        logger.info(f"Starting new session #{self.session_count}")
    
    def random_mouse_movement(self):
        """Simulate random mouse movement pattern"""
        # This would be implemented with actual browser automation
        # For now, just add a small delay to simulate movement time
        movement_time = random.uniform(0.3, 1.5)
        time.sleep(movement_time)
        return movement_time
    
    def random_scroll_pattern(self) -> int:
        """Generate a random scroll pattern"""
        # Simulate human-like scrolling behavior
        scroll_amounts = [3, 5, 8, 5, 3, 7, 4, 6]  # Variable scroll amounts
        total_scroll = 0
        
        num_scrolls = random.randint(3, 8)
        for _ in range(num_scrolls):
            scroll = random.choice(scroll_amounts)
            total_scroll += scroll
            time.sleep(random.uniform(0.5, 2))  # Pause between scrolls
        
        return total_scroll
    
    def get_random_viewport(self) -> Tuple[int, int]:
        """Get a random viewport size"""
        viewports = [
            (1920, 1080),
            (1366, 768),
            (1440, 900),
            (1536, 864),
            (1280, 720),
            (1600, 900),
        ]
        return random.choice(viewports)
    
    def random_page_stay_time(self) -> float:
        """Generate a random time to stay on a page"""
        # Humans typically stay 10-45 seconds on a job listing
        return random.uniform(10, 45)
    
    def should_skip_action(self, probability: float = 0.1) -> bool:
        """Randomly decide to skip an action (humans don't do everything perfectly)"""
        return random.random() < probability
    
    def vary_request_timing(self, base_delay: float) -> float:
        """Add variation to request timing"""
        # Add 10-30% variation
        variation = random.uniform(0.1, 0.3)
        if random.random() < 0.5:
            return base_delay * (1 + variation)
        else:
            return base_delay * (1 - variation)

class RateLimiter:
    """Rate limiter for controlling request frequency"""
    
    def __init__(self, max_requests: int, time_window: int = 3600):
        """
        Args:
            max_requests: Maximum number of requests allowed
            time_window: Time window in seconds (default 1 hour)
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def can_make_request(self) -> bool:
        """Check if a request can be made"""
        now = time.time()
        # Remove old requests outside the time window
        self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
        
        return len(self.requests) < self.max_requests
    
    def wait_time(self) -> float:
        """Get the time to wait before next request is allowed"""
        if self.can_make_request():
            return 0
        
        now = time.time()
        oldest_request = min(self.requests)
        return max(0, self.time_window - (now - oldest_request))
    
    def record_request(self):
        """Record that a request was made"""
        self.requests.append(time.time())
    
    def wait_if_needed(self):
        """Wait if rate limited"""
        wait = self.wait_time()
        if wait > 0:
            logger.info(f"Rate limit reached. Waiting {wait:.0f} seconds...")
            time.sleep(wait + 1)  # Add 1 second buffer

def get_random_delay_range(platform: str = "default") -> Tuple[float, float]:
    """Get platform-specific delay ranges"""
    ranges = {
        "linkedin": (3, 7),
        "indeed": (2, 5),
        "welcometothejungle": (4, 8),
        "default": (3, 8)
    }
    return ranges.get(platform, ranges["default"])
