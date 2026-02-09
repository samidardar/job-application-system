"""
Logging utilities for the job application system
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/system.log",
    max_file_size: int = 10*1024*1024,  # 10MB
    backup_count: int = 5,
    log_to_console: bool = True
) -> logging.Logger:
    """Setup logging configuration"""
    
    # Create logs directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers = []
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_file_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

def get_agent_logger(agent_name: str) -> logging.Logger:
    """Get logger for a specific agent"""
    logger = logging.getLogger(f"agent.{agent_name}")
    return logger

class ActivityLogger:
    """Logs agent activities to both file and database"""
    
    def __init__(self, agent_name: str, db_manager=None):
        self.agent_name = agent_name
        self.logger = get_agent_logger(agent_name)
        self.db = db_manager
    
    def log(self, action: str, status: str = "info", details: str = None):
        """Log an activity"""
        message = f"[{self.agent_name}] {action}"
        if details:
            message += f" - {details}"
        
        # Log to file
        if status.lower() == "error":
            self.logger.error(message)
        elif status.lower() == "warning":
            self.logger.warning(message)
        else:
            self.logger.info(message)
        
        # Log to database if available
        if self.db:
            try:
                self.db.log_activity(self.agent_name, action, status, details)
            except Exception as e:
                self.logger.error(f"Failed to log to database: {e}")
    
    def info(self, action: str, details: str = None):
        self.log(action, "success", details)
    
    def error(self, action: str, details: str = None):
        self.log(action, "error", details)
    
    def warning(self, action: str, details: str = None):
        self.log(action, "warning", details)
