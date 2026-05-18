import logging
import os
from logging.handlers import RotatingFileHandler

DEBUG = False
logger = None


def setup_logging(log_dir=None):
    global logger
    _log_dir = log_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    os.makedirs(_log_dir, exist_ok=True)
    _log_file = os.path.join(_log_dir, 'orchestrator.log')

    logger = logging.getLogger('orchestrator')
    logger.setLevel(logging.DEBUG)

    _file_handler = RotatingFileHandler(
        _log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    _file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-5s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(_file_handler)
    logger.info("=== Orchestrator session started ===")


def log_and_print(msg: str, level: str = 'info', console: bool = True):
    """Log to file always; print to terminal if console=True."""
    if logger:
        getattr(logger, level)(msg)
    if console:
        print(msg)
