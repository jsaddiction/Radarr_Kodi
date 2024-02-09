"""Radarr Environment parser"""

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import get_args, get_origin, Any
from os import environ


class Events(Enum):
    """Radarr Events"""

    ON_GRAB = "Grab"
    ON_DOWNLOAD = "Download"
    ON_RENAME = "Rename"
    ON_MOVIE_ADD = "MovieAdded"
    ON_MOVIE_DELETE = "MovieDelete"
    ON_MOVIE_FILE_DELETE = "MovieFileDelete"
    ON_HEALTH_ISSUE = "HealthIssue"
    ON_HEALTH_RESTORED = "HealthRestored"
    ON_APPLICATION_UPDATE = "ApplicationUpdate"
    ON_MANUAL_INTERACTION_REQUIRED = "ManualInteractionRequired"
    ON_TEST = "Test"
    UNKNOWN = "Unknown"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        value = value.upper()
        for member in cls:
            if member.value.upper() == value:
                return member
        return cls.UNKNOWN


@dataclass
class RadarrEnvironment:
    """Radarr Environment Variables"""

    event_type: Events = field(default=Events.UNKNOWN, metadata={"var": "Radarr_EventType"})
    movie_title: str = field(default=None, metadata={"var": "Radarr_Movie_Title"})
    movie_year: int = field(default=None, metadata={"var": "Radarr_Movie_Year"})
    movie_tmdbid: int = field(default=None, metadata={"var": "Radarr_Movie_tmdbid"})
    is_upgrade: bool = field(default=None, metadata={"var": "Radarr_IsUpgrade"})
    movie_file_dir: str = field(default=None, metadata={"var": "Radarr_Movie_Path"})  # Directory of the movie file
    movie_file_path: str = field(default=None, metadata={"var": "Radarr_MovieFile_Path"})  # Full path to the movie file
    movie_folder_size: int = field(
        default=None, metadata={"var": "Radarr_Movie_Folder_Size"}
    )  # Size of the movie folder
    # On_Download (upgrades) '|' delimited list of deleted paths
    movie_file_deleted_paths: list[str] = field(default_factory=list, metadata={"var": "Radarr_DeletedPaths"})
    # On_Rename '|' delimited list of previous paths
    movie_file_prev_paths: list[str] = field(default_factory=list, metadata={"var": "Radarr_MovieFile_PreviousPaths"})
    movie_file_paths: list[str] = field(default_factory=list, metadata={"var": "Radarr_MovieFilePaths"})  # On_Rename
    movie_file_delete_reason: str = field(default=None, metadata={"var": "Radarr_MovieFile_DeleteReason"})
    # this might need to be a bool type
    movie_deleted_files: str = field(default=None, metadata={"var": "Radarr_Movie_DeletedFiles"})
    health_issue_msg: str = field(default=None, metadata={"var": "Radarr_Health_Issue_Message"})
    health_restored_msg: str = field(default=None, metadata={"var": "Radarr_Health_Restored_Message"})
    update_message: str = field(default=None, metadata={"var": "Radarr_Update_Message"})
    raw_vars: dict = field(default=None, repr=False)

    @classmethod
    def _parse_bool(cls, value: str) -> bool:
        if isinstance(value, str):
            if value.lower().strip() == "true":
                return True
            if value.lower().strip() == "false":
                return False

        raise ValueError(f"Failed to parse '{value}' to a boolean")

    @classmethod
    def _parse_int(cls, value: str) -> int:
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                pass

        raise ValueError(f"Failed to parse {value} to int")

    def __post_init__(self) -> None:
        # Get environment variables
        self.raw_vars = {k.lower().strip(): v for k, v in environ.items() if k.lower().startswith("radarr")}

        # Loop through dataclass fields
        for attr in fields(self):
            var_name = attr.metadata.get("var")
            if not var_name:
                continue

            value = self.raw_vars.get(var_name.lower())
            if not value:
                continue

            # Based on attribute type, store this environment variable's value
            if issubclass(attr.type, Events):
                self.__setattr__(attr.name, Events(value))

            elif issubclass(attr.type, str):
                self.__setattr__(attr.name, value.strip())

            elif issubclass(attr.type, bool):
                self.__setattr__(attr.name, self._parse_bool(value))

            elif issubclass(attr.type, int):
                self.__setattr__(attr.name, self._parse_int(value))

            # Handle lists
            elif get_origin(attr.type) == list:
                list_type = get_args(attr.type)[0]

                # List of strings
                if issubclass(list_type, str):
                    value_lst = [x.strip() for x in value.split("|")]
                    self.__setattr__(attr.name, value_lst)

                # List of integers
                elif issubclass(list_type, int):
                    value_lst = [self._parse_int(x) for x in value.split(",")]
                    self.__setattr__(attr.name, value_lst)
