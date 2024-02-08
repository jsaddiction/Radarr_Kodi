"""Radarr Kodi Config Models"""

from dataclasses import dataclass, field
from typing import Any, Type, Self, Tuple
from enum import Enum


class LogLevels(Enum):
    """Supported Logging Levels"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @classmethod
    def values(cls) -> list[str]:
        """List of values within LogLevels"""
        return [member.value for member in cls]

    @classmethod
    def _missing_(cls, value: object) -> Any:
        value = value.upper()
        for member in cls:
            if member.value == value:
                return member
        return None


@dataclass
class LogCfg:
    """Log Config"""

    level: LogLevels = field(metadata={"type": str})
    write_file: bool = field(metadata={"type": bool})

    @classmethod
    def from_dict(cls: Type["LogCfg"], data: dict) -> Self:
        """Get Instance from dict values"""

        # Parse into dataclass
        return cls(level=LogLevels(data["level"]).value, write_file=data["write_file"])


@dataclass
class PathMapping:
    """Radarr to Host path maps"""

    radarr: str
    kodi: str


@dataclass
class LibraryCfg:
    """Library Config"""

    clean_after_update: bool
    skip_active: bool
    full_scan_fallback: bool
    wait_for_nfo: bool
    nfo_timeout_minuets: int
    path_mapping: list[PathMapping] = field(default_factory=list)

    @classmethod
    def from_dict(cls: Type["LibraryCfg"], data: dict) -> Self:
        """Get Instance from dict values"""

        # Parse into dataclass
        path_maps = data.pop("path_mapping", None)
        library_cfg = cls(**data)
        if path_maps:
            library_cfg.path_mapping = [PathMapping(**x) for x in path_maps]

        return library_cfg


@dataclass
class Notifications:
    """Notification Config"""

    on_grab: bool
    on_download_new: bool
    on_download_upgrade: bool
    on_rename: bool
    on_delete: bool
    on_movie_add: bool
    on_movie_delete: bool
    on_health_issue: bool
    on_health_restored: bool
    on_application_update: bool
    on_manual_interaction_required: bool
    on_test: bool


@dataclass
class HostConfig:
    """Kodi Host Config"""

    name: str
    ip_addr: str
    port: int
    user: str
    password: str
    enabled: bool
    disable_notifications: bool
    priority: int

    @property
    def credentials(self) -> Tuple[str, str]:
        """Tuple of credentials"""
        return (self.user, self.password)

    @classmethod
    def from_dict(cls: Type["HostConfig"], data: dict) -> Self:
        """Get Instance from dict values"""
        return cls(
            name=data["name"],
            ip_addr=data["ip_addr"],
            port=data["port"],
            user=data["user"],
            password=data["password"],
            enabled=data["enabled"],
            disable_notifications=data["disable_notifications"],
            priority=data["priority"],
        )


@dataclass
class Config:
    """Configuration Model"""

    logs: LogCfg = field(default_factory=LogCfg)
    library: LibraryCfg = field(default_factory=LibraryCfg)
    notifications: Notifications = field(default_factory=Notifications)
    hosts: list[HostConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls: Type["Config"], data: dict) -> Self:
        """Get Instance from dict values"""

        # Parse into dataclass
        return cls(
            logs=LogCfg.from_dict(data["logs"]),
            library=LibraryCfg.from_dict(data["library"]),
            notifications=Notifications(**data["notifications"]),
            hosts=[HostConfig.from_dict(x) for x in data["hosts"]],
        )
