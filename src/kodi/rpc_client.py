"""Kodi JSON-RPC Interface"""

import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import PurePosixPath, PureWindowsPath
import requests
from .exceptions import APIError, ScanTimeout
from .models import (
    RPCVersion,
    Platform,
    KodiResponse,
    WatchedState,
    ResumeState,
    MovieDetails,
    Player,
    PlayerItem,
    MOVIE_PROPERTIES,
)


class KodiRPC:
    """Kodi JSON-RPC Client"""

    RETRIES = 3
    TIMEOUT = 5
    HEADERS = {"Content-Type": "application/json", "Accept": "plain/text"}

    def __init__(
        self,
        name: str,
        ip_addr: str,
        port: int = 8080,
        user: str = None,
        password: str = None,
        disable_notifications: bool = False,
        priority: int = 0,
        path_maps: list[dict] = None,
    ) -> None:
        self.log = logging.getLogger(f"Kodi.{name}")
        self.base_url = f"http://{ip_addr}:{port}/jsonrpc"
        self.name = name
        self.disable_notifications = disable_notifications
        self.priority = priority
        self.path_maps = path_maps
        self.library_scanned = False
        self._platform: Platform = None

        # Establish session
        self.session = requests.Session()
        if user and password:
            self.session.auth = (user, password)
        self.session.headers.update(self.HEADERS)
        self.req_id = 0

    def __str__(self) -> str:
        return f"{self.name} JSON-RPC({self.rpc_version})"

    @property
    def platform(self) -> Platform:
        """Get platform of this client"""
        if self._platform:
            return self._platform

        params = {"booleans": [x.value for x in Platform]}
        try:
            resp = self._req("XBMC.GetInfoBooleans", params=params)
        except APIError as e:
            self.log.warning("Failed to get platform info. Error: %s", e)
            self._platform = Platform.UNKNOWN
            return self._platform

        # Check all platform booleans and return the first one that is True
        for k, v in resp.result.items():
            if v:
                return Platform(k)

        # Return unknown if no platform booleans are True
        self._platform = Platform.UNKNOWN
        return self._platform

    @property
    def rpc_version(self) -> RPCVersion | None:
        """Return JSON-RPC Version of host"""
        try:
            resp = self._req("JSONRPC.Version")
        except APIError as e:
            self.log.warning("Failed to get JSON-RPC Version. Error: %s", e)
            return None

        return RPCVersion(
            major=resp.result["version"].get("major"),
            minor=resp.result["version"].get("minor"),
            patch=resp.result["version"].get("patch"),
        )

    @property
    def is_alive(self) -> bool:
        """Return True if Kodi Host is responsive"""
        try:
            resp = self._req("JSONRPC.Ping")
        except APIError as e:
            self.log.warning("Failed to ping host. Error: %s", e)
            return False

        return resp.result == "pong"

    @property
    def is_playing(self) -> bool:
        """Return True if Kodi Host is currently playing content"""
        return bool(self.active_players)

    @property
    def active_players(self) -> list[Player]:
        """Get a list of active players"""
        try:
            resp = self._req("Player.GetActivePlayers")
        except APIError as e:
            self.log.warning("Failed to get active players. Error: %s", e)
            return []

        active_players: list[Player] = []
        for active_player in resp.result:
            active_players.append(
                Player(
                    player_id=active_player["playerid"],
                    player_type=active_player["playertype"],
                    type=active_player["type"],
                )
            )

        return active_players

    @property
    def is_scanning(self) -> bool:
        """True if a library scan is in progress"""
        params = {"booleans": ["Library.IsScanning"]}
        try:
            resp = self._req("XBMC.GetInfoBooleans", params=params)
        except APIError as e:
            self.log.warning("Failed to determine scanning state. Error: %s", e)
            return False

        return resp.result["Library.IsScanning"]

    @property
    def is_posix(self) -> bool:
        """If this host uses posix file naming conventions"""
        return self.platform not in [Platform.WINDOWS, Platform.UNKNOWN]

    @staticmethod
    def _to_dt(dt_str: str) -> datetime | None:
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return None

    @staticmethod
    def _parse_movie_details(movie_data: dict) -> MovieDetails | None:
        try:
            return MovieDetails(
                movie_id=movie_data["movieid"],
                file=movie_data["file"],
                title=movie_data["title"],
                year=movie_data["year"],
                imdb=movie_data["uniqueid"].get("imdb"),
                tmdb=movie_data["uniqueid"].get("tmdb"),
                watched_state=WatchedState(
                    play_count=movie_data["playcount"],
                    date_added=KodiRPC._to_dt(movie_data["dateadded"]),
                    last_played=KodiRPC._to_dt(movie_data["lastplayed"]),
                    resume=ResumeState(
                        position=movie_data["resume"]["position"],
                        total=movie_data["resume"]["total"],
                    ),
                ),
            )
        except KeyError:
            return None

    # --------------- Helper Methods -----------------
    def _map_path(self, path: str) -> str:
        """Map path from Radarr to Kodi path using path_maps"""
        out_str = path
        for mapping in self.path_maps:
            if mapping["radarr"] in path:
                out_str = path.replace(mapping["radarr"], mapping["kodi"])
                break

        if self.is_posix:
            return str(PurePosixPath(out_str))

        return str(PureWindowsPath(out_str))

    def _get_filename_from_path(self, path: str) -> str:
        """Extract filename from path based on os type"""
        if self.is_posix:
            return str(PurePosixPath(path).name)
        return str(PureWindowsPath(path).name)

    def _get_dirname_from_path(self, path: str) -> str:
        """Extract dir name from path based on os type"""
        if self.is_posix:
            return str(PurePosixPath(path).parent)
        return str(PureWindowsPath(path).parent)

    def _wait_for_video_scan(self, max_secs: int = 1800) -> timedelta:
        """Wait for video scan to complete"""
        # Default timeout = 30 Min
        start = datetime.now()
        self.log.debug("Waiting up to %s minuets for library scan to complete", max_secs / 60)
        while True:
            elapsed = datetime.now() - start

            # Check if scanning, may raise APIError if failed to communicate
            if not self.is_scanning:
                return elapsed

            # Break out if time limit exceeded
            if elapsed.total_seconds() >= max_secs:
                raise ScanTimeout(f"Waited for {elapsed}. Giving up.")

            # Sleep for 100ms before checking again
            time.sleep(0.1)

    def _req(self, method: str, params: dict = None, timeout: int = None) -> KodiResponse | None:
        """Send request to this Kodi Host"""
        req_params = {"jsonrpc": "2.0", "id": self.req_id, "method": method}
        if params:
            req_params["params"] = params
        response = None
        try:
            resp = self.session.post(
                url=self.base_url,
                data=json.dumps(req_params).encode("utf-8"),
                timeout=timeout or self.TIMEOUT,
            )
            resp.raise_for_status()
            response = resp.json()
        except requests.Timeout as e:
            raise APIError(f"Request timed out after {timeout}s") from e
        except requests.HTTPError as e:
            if resp.status_code == 401:
                raise APIError("HTTP Error. Unauthorized. Check Credentials") from e
            raise APIError(f"HTTP Error. Error: {e}") from e
        except requests.ConnectionError as e:
            raise APIError(f"Connection Error. {e}") from e
        finally:
            self.req_id += 1

        if "error" in response:
            raise APIError(response.get("error"))

        return KodiResponse(
            req_id=response.get("id"),
            jsonrpc=response.get("jsonrpc"),
            result=response.get("result"),
        )

    def close_session(self) -> None:
        """Close the session"""
        self.log.debug("Closing session")
        self.session.close()

    # --------------- UI Methods ---------------------
    def update_gui(self) -> None:
        """Update GUI|Widgets by scanning a non existent path"""
        params = {"directory": "/does_not_exist/", "showdialogs": False}
        self.log.info("Updating GUI")
        try:
            self._req("VideoLibrary.Scan", params=params)
        except APIError as e:
            self.log.warning("Failed to update GUI. Error: %s", e)

    def notify(self, title: str, msg: str, force: bool = False, display_time: int = 5000) -> None:
        """Send GUI Notification to Kodi Host"""
        # Skip if notifications are disabled and not forced
        if self.disable_notifications and not force:
            self.log.debug("All Host GUI Notifications disabled. Skipping.")
            return

        params = {
            "title": str(title),
            "message": str(msg),
            "displaytime": int(display_time),
            "image": "https://github.com/jsaddiction/Radarr_Kodi/raw/main/img/Radarr.png",
        }
        self.log.info("Sending GUI Notification :: title='%s', msg='%s'", title, msg)
        try:
            self._req("GUI.ShowNotification", params=params)
        except APIError as e:
            self.log.warning("Failed to send notification. Error: %s", e)

    # --------------- Player Methods -----------------
    def is_paused(self, player_id: int) -> bool:
        """Return True if player is currently paused"""
        # If player is stopped, speed is 0 (paused). Check for playing first.
        if not self.is_playing:
            return False

        params = {"playerid": player_id, "properties": ["speed"]}
        try:
            resp = self._req("Player.GetProperties", params=params)
        except APIError as e:
            self.log.warning("Failed to determine paused state of player. Error: %s", e)
            return False

        return int(resp.result["speed"]) == 0

    def player_percent(self, player_id: int) -> float:
        """Return Position of player in percent complete"""
        params = {"playerid": player_id, "properties": ["percentage"]}
        try:
            resp = self._req("Player.GetProperties", params=params)
        except APIError as e:
            self.log.warning("Failed to get player position. Error: %s", e)
            return 0.0

        return resp.result.get("percentage", 0.0)

    def get_player_item(self, player_id: int) -> PlayerItem | None:
        """Get items a given player is playing"""
        params = {"playerid": player_id}
        try:
            resp = self._req("Player.GetItem", params=params)
        except APIError as e:
            self.log.warning("Failed to get player item. Error: %s", e)
            return None

        try:
            return PlayerItem(
                item_id=resp.result["item"]["id"],
                label=resp.result["item"]["label"],
                type=resp.result["item"]["type"],
            )
        except KeyError:
            return None

    def pause_player(self, player_id: int, max_retries: int = 3) -> None:
        """Pauses a player"""
        params = {"playerid": player_id}
        for _ in range(max_retries):
            try:
                resp = self._req("Player.PlayPause", params=params)
            except APIError as e:
                self.log.warning("Failed to pause player. Error: %s", e)
                return

            if resp.result["speed"] == 0:
                return
        self.log.warning("Failed to pause player after %s retries", max_retries)

    def stop_player(self, player_id: int) -> None:
        """Stops a player"""
        params = {"playerid": player_id}
        try:
            self._req("Player.Stop", params=params)
        except APIError as e:
            self.log.warning("Failed to stop player. Error: %s", e)

    def start_movie(self, movie_id: int, position: float) -> Player | None:
        """Play a given movie and return the player object"""
        self.log.info("Restarting Movie %s", movie_id)
        params = {"item": {"movieid": movie_id}, "options": {"resume": position}}
        try:
            self._req("Player.Open", params=params)
        except APIError as e:
            self.log.warning("Failed to start movie. Error: %s", e)
            return None

        # Wait for player to start
        start = datetime.now()
        while True:
            for player in self.active_players:
                item = self.get_player_item(player.player_id)
                if item and item.type == "movie" and item.item_id == movie_id:
                    return player

            # Break out if time limit exceeded
            if (datetime.now() - start).total_seconds() > 5:
                self.log.warning("Movie failed to start after 5 second. Giving up.")
                return None

    # --------------- Library Methods ----------------
    def scan_movie_dir(self, directory: str) -> bool:
        """Scan a directory"""
        # Ensure trailing slash
        mapped_path = self._map_path(directory)
        mapped_path = mapped_path.rstrip("/") + "/"
        params = {"directory": mapped_path, "showdialogs": False}

        # Scan the Directory
        self.log.info("Scanning directory '%s'", mapped_path)
        try:
            self._req("VideoLibrary.Scan", params=params)
        except APIError as e:
            self.log.warning("Failed to scan %s. Error: %s", mapped_path, e)
            return False

        # Wait for library to scan
        try:
            elapsed = self._wait_for_video_scan(max_secs=120)
        except ScanTimeout as e:
            self.log.warning("Scan timed out. Error: %s", e)
            return False

        self.log.info("Scan completed in %s", elapsed)
        self.library_scanned = True
        return True

    def full_video_scan(self) -> bool:
        """Perform full video library scan"""
        params = {"showdialogs": False}
        self.log.info("Performing full library scan")
        try:
            self._req("VideoLibrary.Scan", params=params)
        except APIError as e:
            self.log.warning("Failed to scan full library. Error: %s", e)
            return False

        try:
            elapsed = self._wait_for_video_scan()
        except ScanTimeout as e:
            self.log.warning("Scan timed out. Error: %s", e)
            return False

        self.log.info("Scan completed in %s", elapsed)
        self.library_scanned = True
        return True

    def clean_video_library(self) -> bool:
        """Clean Video Library"""
        # Passing a movie_dir does not initiate clean. With or without trailing '/'
        # Preferably, should set {'directory': movie_dir} vice {'content': 'movies'}
        params = {"showdialogs": False, "content": "movies"}

        self.log.info("Cleaning Movie library.")
        try:
            self._req("VideoLibrary.Clean", params=params)
        except APIError as e:
            self.log.warning("Failed to clean library. Error: %s", e)
            return False

        # Wait for cleaning to complete
        try:
            elapsed = self._wait_for_video_scan(max_secs=300)
        except ScanTimeout as e:
            self.log.warning("Library Clean timed out. Error: %s", e)
            return False

        self.log.info("Library Clean completed in %s", elapsed)
        self.library_scanned = True
        return True

    # --------------- Movie Methods ------------------
    def set_movie_watched_state(self, movie: MovieDetails, new_movie_id: int) -> bool:
        """Set Movie Watched State"""
        self.log.debug("Setting watched state %s on %s", movie.watched_state, movie)
        params = {
            "movieid": new_movie_id,
            "playcount": movie.watched_state.play_count,
            "lastplayed": movie.watched_state.last_played_str,
            "dateadded": movie.watched_state.date_added_str,
            "resume": {
                "position": movie.watched_state.resume.position,
                "total": movie.watched_state.resume.total,
            },
        }

        try:
            self._req("VideoLibrary.SetMovieDetails", params=params)
        except APIError as e:
            self.log.warning("Failed to set movie metadata. Error: %s", e)
            return False

        return True

    def get_all_movies(self) -> list[MovieDetails]:
        """Get all movies in library"""
        self.log.debug("Getting all movies")
        params = {"properties": MOVIE_PROPERTIES}
        try:
            resp = self._req("VideoLibrary.GetMovies", params=params, timeout=60)
        except APIError as e:
            self.log.warning("Failed to get all movies. Error: %s", e)
            return []

        return [self._parse_movie_details(x) for x in resp.result["movies"]]

    def get_movies_by_dir(self, directory: str) -> list[MovieDetails]:
        """Get all movies in a directory"""
        mapped_path = self._map_path(directory)
        params = {
            "properties": MOVIE_PROPERTIES,
            "filter": {"operator": "startswith", "field": "path", "value": mapped_path},
        }

        self.log.debug("Getting all movies from path %s", mapped_path)
        try:
            resp = self._req("VideoLibrary.GetMovies", params=params)
        except APIError as e:
            self.log.warning("Failed to get movies from file '%s'. Error: %s", mapped_path, e)
            return []

        return [self._parse_movie_details(x) for x in resp.result["movies"]]

    def get_movies_by_file(self, path: str) -> list[MovieDetails]:
        """Get all movies given a file path"""
        mapped_path = self._map_path(path)
        file_name = self._get_filename_from_path(mapped_path)
        file_dir = self._get_dirname_from_path(mapped_path)
        params = {
            "properties": MOVIE_PROPERTIES,
            "filter": {
                "and": [
                    {"operator": "startswith", "field": "path", "value": file_dir},
                    {"operator": "is", "field": "filename", "value": file_name},
                ]
            },
        }

        self.log.debug("Getting all movies from path %s", mapped_path)
        try:
            resp = self._req("VideoLibrary.GetMovies", params=params)
        except APIError as e:
            self.log.warning("Failed to get movies from file '%s'. Error: %s", mapped_path, e)
            return []

        return [self._parse_movie_details(x) for x in resp.result["movies"]]

    def remove_movie(self, movie_id: int) -> bool:
        """Remove a movie from library and return it's details"""
        params = {"movieid": movie_id}
        self.log.debug("Removing movie with movie id %s", movie_id)
        try:
            self._req("VideoLibrary.RemoveMovie", params=params)
        except APIError as e:
            self.log.warning("Failed to remove movie by id '%s'. Error: %s", movie_id, e)
            return False

        self.library_scanned = True
        return True
