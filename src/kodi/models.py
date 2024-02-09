"""Response Models for Kodi JSON-RPC"""

from enum import Enum
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime


DT_FORMAT = "%Y-%m-%d %H:%M:%S"
MOVIE_PROPERTIES = [
    "lastplayed",
    "playcount",
    "file",
    "dateadded",
    "title",
    "year",
    "resume",
    "uniqueid",
]


class Platform(Enum):
    """Kodi Platform enumeration"""

    ANDROID = "System.Platform.Android"
    DARWIN = "System.Platform.Darwin"
    IOS = "System.Platform.IOS"
    LINUX = "System.Platform.Linux"
    OSX = "System.Platform.OSX"
    TVOS = "System.Platform.TVOS"
    UWP = "System.Platform.UWP"
    WINDOWS = "System.Platform.Windows"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, order=True)
class RPCVersion:
    """JSON-RPC Version info"""

    major: int
    minor: int
    patch: int = field(compare=False)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass
class KodiResponse:
    """Kodi JSON-RPC Response Model"""

    req_id: int
    jsonrpc: str
    result: Optional[dict] | None = field(default=None)


@dataclass
class Player:
    """A Content player"""

    player_id: int
    player_type: str
    type: str


@dataclass
class PlayerItem:
    """What the player is playing"""

    item_id: int
    label: str
    type: str


@dataclass(slots=True)
class ResumeState:
    """Resume Point of a Media Item"""

    position: int = field(default=0)
    total: int = field(default=0)

    @property
    def percent(self) -> float:
        """Percent complete"""
        if self.total == 0 or self.position == 0:
            return 0.0

        return (self.position / self.total) * 100

    def __str__(self) -> str:
        return f"Resume {self.percent:.2f}% Complete."


@dataclass(slots=True)
class WatchedState:
    """Watched State of a Media Item"""

    play_count: int | None = field(default=None)
    date_added: datetime | None = field(default=None)
    last_played: datetime | None = field(default=None)
    resume: ResumeState = field(default_factory=ResumeState)

    @property
    def date_added_str(self) -> str:
        """Formatted Date Added DT"""
        if not self.date_added:
            return ""
        return self.date_added.strftime(DT_FORMAT)

    @property
    def last_played_str(self) -> str:
        """Formatted Last Played DT"""
        if not self.last_played:
            return ""
        return self.last_played.strftime(DT_FORMAT)

    @property
    def is_watched(self) -> bool:
        """If this state represents watched"""
        if self.play_count is None:
            return False
        if not self.last_played:
            return False

        return bool(self.last_played) and self.play_count > 0

    def __str__(self) -> str:
        return f"Added={self.date_added} Plays={self.play_count} LastPlay={self.last_played} {self.resume}"


@dataclass(frozen=True, order=False, eq=True, slots=True)
class MovieDetails:
    """Details of a Movie"""

    movie_id: int = field(compare=False, hash=False)
    file: str = field(compare=False, hash=False)
    title: str = field(compare=False, hash=False)
    year: int = field(compare=False, hash=False)
    watched_state: WatchedState = field(compare=False, hash=False)
    imdb: str = field(default=None, compare=False, hash=False)
    tmdb: str = field(default=None, compare=True, hash=False)

    def __str__(self) -> str:
        return f"{self.title} ({self.year})"


@dataclass(frozen=True)
class StoppedMovie:
    """Episode that was playing during delete event"""

    movie: MovieDetails
    host_name: str
    position: float
    paused: bool

    def __str__(self) -> str:
        return f"{self.movie} on {self.host_name} stopped at {self.position:.2f}%"
