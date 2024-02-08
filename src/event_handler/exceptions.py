"""Event handler exceptions"""

from pathlib import Path
from datetime import timedelta


class NFOTimeout(Exception):
    """Timed out while waiting for NFO to be created"""

    def __init__(self, elapsed_time: timedelta, missing_nfo: Path, *args: object) -> None:
        super().__init__(*args)
        self.missing_nfo: Path = missing_nfo
        self.elapsed_time: timedelta = elapsed_time

    def __str__(self) -> str:
        return f"NFO Timeout after {self.elapsed_time} while waiting for '{self.missing_nfo}'."
