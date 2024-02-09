"""Radarr Kodi"""

import logging
import logging.config
from pathlib import Path
from .config import ConfigParser
from .environment import Events, ENV
from .kodi import LibraryManager
from .event_handler import EventHandler
from .config.models import LogCfg

__all__ = ["ConfigParser", "LibraryManager", "Events", "ENV", "EventHandler"]


def _get_log_path() -> str:
    """Determine where to store logs"""
    file_path = "/config/logs"
    file_name = "Radarr_Kodi.txt"

    if not Path(file_path).exists():
        # Create and return a /logs directory within this package
        log_dir = Path(__file__).resolve().parent.parent / "logs"
        if not log_dir.exists():
            log_dir.mkdir()
        return str(Path(log_dir, file_name))

    # Return the default Radarr logs directory
    return str(Path(file_path, file_name))


def config_log(log_cfg: LogCfg) -> None:
    """Configure logging"""
    file_handler = {
        "class": "logging.handlers.RotatingFileHandler",
        "level": log_cfg.level,
        "formatter": "file",
        "filename": _get_log_path(),
        "maxBytes": 1_000_000,
        "backupCount": 5,
    }
    default_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "file": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
            "console": {
                "format": "%(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "console",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "root": {
                "handlers": ["console"],
                "level": "DEBUG",
            }
        },
    }

    if log_cfg.write_file:
        default_config["handlers"]["file"] = file_handler
        default_config["loggers"]["root"]["handlers"].append("file")

    logging.config.dictConfig(default_config)
