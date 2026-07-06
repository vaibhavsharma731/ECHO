import os
import logging
from app.services.config.config_manager import config_manager

def setup_logger(name="ECHO"):
    """
    Sets up a logger that prints messages to BOTH the console and a file.
    This is like the notebook where the chef logs kitchen activity.
    """
    # 1. Get logging settings from our ConfigManager
    log_level_str = config_manager.get("logging.level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    log_dir = config_manager.get("logging.log_dir", "data/logs")
    
    # 2. Get absolute path of project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    full_log_dir = os.path.join(project_root, log_dir)
    log_file = os.path.join(full_log_dir, "echo.log")
    
    # 3. Create the logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Avoid adding duplicate handlers if setup is called multiple times
    if logger.handlers:
        return logger
        
    # 4. Create formatting for the logs (timestamp - name - level - message)
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 5. File handler (writes logs to file)
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to create file log handler: {e}")
        
    # 6. Stream handler (prints logs to console/terminal)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(log_level)
    logger.addHandler(stream_handler)
    
    return logger

# Generate a default logger we can import and use right away
logger = setup_logger("ECHO")
