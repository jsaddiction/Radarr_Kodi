"""Radarr_Kodi Event handler"""

import logging
from datetime import datetime
from pathlib import Path
from src.environment import RadarrEnvironment
from src.config import Config
from src.kodi import LibraryManager
from .exceptions import NFOTimeout


class EventHandler:
    """Handles Radarr Events and deploys Kodi JSON-RPC calls"""

    def __init__(self, env: RadarrEnvironment, cfg: Config, kodi: LibraryManager) -> None:
        self.env = env
        self.cfg = cfg
        self.kodi = kodi
        self.log = logging.getLogger("EventHandler")

    # ------------- Helpers --------------------
    def _wait_for_nfo(self, nfo: Path, timeout_min: int) -> None:
        """Wait for file provided to be present in the file system.

        Args:
            nfos (Path): Path objects to check
            timeout_min (int): Number of minuets to wait

        Raises:
            NFOTimeout: Contains the elapsed time and missing filenames if timeout_min * len(nfos) exceeded
        """
        max_sec = timeout_min * 60
        self.log.info("Waiting up to %s minuets for NFO File.", timeout_min)

        start = datetime.now()
        while True:
            elapsed = datetime.now() - start

            # Check if NFO exists
            if nfo.exists():
                self.log.debug("Found %s", nfo.name)
                break

            # Raise timeout if wait exceeds max_sec
            if elapsed.total_seconds() >= max_sec:
                raise NFOTimeout(elapsed_time=elapsed, missing_nfo=nfo)

        self.log.info("All required NFO files were found after %s.", elapsed)

    # ------------- Events -------------------------
    def grab(self) -> None:
        """Grab Events"""
        self.log.info("Grab Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_grab:
            self.log.info("Grab notifications disabled. Skipping.")
            return

        # Send notification for each attempted download
        title = "Radarr - Attempting Download"
        self.kodi.notify(title=title, msg=f"{self.env.movie_title} ({self.env.movie_year})")

    def download_new(self) -> None:
        """Downloaded a new Movie"""
        self.log.info("Download New Movie Event Detected")

        # Optionally, wait for NFO files to generate
        if self.cfg.library.wait_for_nfo:
            movie_nfo = Path(self.env.movie_file_path).with_suffix(".nfo")
            try:
                self._wait_for_nfo(movie_nfo, self.cfg.library.nfo_timeout_minuets)
            except NFOTimeout as e:
                self.log.critical(e)
                return

        # Scan for new movies
        new_movies = self.kodi.scan_directory(self.env.movie_file_dir, skip_active=self.cfg.library.skip_active)
        if not new_movies and self.cfg.library.full_scan_fallback:
            new_movies = self.kodi.full_scan(skip_active=self.cfg.library.skip_active)

        # Optionally, Clean Library
        if self.cfg.library.clean_after_update:
            self.kodi.clean_library()

        # Exit early if nothing was scanned into the library
        if not new_movies:
            self.log.warning("No movies were scanned into library. Exiting.")
            return

        self.log.info("Scan found %s new movie[s].", len(new_movies))

        # Update GUI on clients not previously scanned
        self.kodi.update_guis()

        # Skip notifications if disabled
        if not self.cfg.notifications.on_download_new:
            self.log.info("Download New Movie notifications disabled. Skipping.")
            return

        # Notify clients
        title = "Radarr - Downloaded New Movie"
        for movie in new_movies:
            self.kodi.notify(title=title, msg=movie)

    def download_upgrade(self) -> None:
        """Downloaded an upgraded movie file"""
        self.log.info("Upgrade Movie Event Detected")

        # Store library data for replaced episodes and remove those entries
        removed_movies = []
        for path in self.env.movie_file_deleted_paths:
            old_movies = self.kodi.get_movies_by_file(path)
            for mov in old_movies:
                if self.kodi.remove_movie(mov):
                    removed_movies.append(mov)

        # optionally, wait for NFO files to generate
        if self.cfg.library.wait_for_nfo:
            movie_nfo = Path(self.env.movie_file_path).with_suffix(".nfo")
            try:
                self._wait_for_nfo(movie_nfo, self.cfg.library.nfo_timeout_minuets)
            except NFOTimeout as e:
                self.log.critical(e)
                return

        # Force library clean if manual removal failed
        if not removed_movies:
            self.log.warning("Failed to remove old movie. Unable to persist watched states. Cleaning Required.")
            if not self.cfg.library.clean_after_update:
                self.kodi.clean_library(skip_active=self.cfg.library.skip_active)

        # Scan show directory and fall back to full scan if configured
        new_movies = self.kodi.scan_directory(self.env.movie_file_dir, skip_active=self.cfg.library.skip_active)
        if not new_movies and self.cfg.library.full_scan_fallback:
            new_movies = self.kodi.full_scan(skip_active=self.cfg.library.skip_active)

        # Optionally, Clean Library
        if self.cfg.library.clean_after_update:
            self.kodi.clean_library()

        # reapply metadata from old library entries
        for removed_movie in removed_movies:
            for new_movie in new_movies:
                if removed_movie == new_movie:
                    self.kodi.copy_metadata(removed_movie, new_movie)

        # update remaining guis
        self.kodi.update_guis()

        # Restart playback of previously stopped episode5
        for movie in new_movies:
            self.kodi.start_playback(movie)

        # Skip notifications if disabled
        if not self.cfg.notifications.on_download_upgrade:
            self.log.info("Upgrade Movie notifications disabled. Skipping.")
            return

        # notify clients
        title = "Radarr - Upgraded Episode"
        for new_movie in new_movies:
            self.kodi.notify(title=title, msg=new_movie)

    def rename(self) -> None:
        """Renamed an episode file"""
        self.log.info("File Rename Event Detected")

        # Store library data for replaced movies and remove those entries
        removed_movies = []
        for path in self.env.movie_file_prev_paths:
            old_movies = self.kodi.get_movies_by_file(path)

            # Stop playback and remove movies
            for old_movie in old_movies:
                self.kodi.stop_playback(old_movie, reason="Rename in progress. Please wait...")
                if self.kodi.remove_movie(old_movie):
                    removed_movies.append(old_movie)

        # Optionally, wait for nfo files to be created
        if self.cfg.library.wait_for_nfo:
            for nfo in [Path(x).with_suffix(".nfo") for x in self.env.movie_file_paths]:
                try:
                    self._wait_for_nfo(nfo, self.cfg.library.nfo_timeout_minuets)
                except NFOTimeout as e:
                    self.log.critical(e)
                    return

        # Force library clean if manual removal failed
        if not removed_movies:
            self.log.warning("Failed to remove old movies. Unable to persist watched states. Cleaning Required.")
            if not self.cfg.library.clean_after_update:
                self.kodi.clean_library(skip_active=self.cfg.library.skip_active)

        # Scan for new movies
        new_movies = self.kodi.scan_directory(self.env.movie_file_dir, skip_active=self.cfg.library.skip_active)

        # Fall back to full library scan
        if not new_movies and self.cfg.library.full_scan_fallback:
            new_movies = self.kodi.full_scan(skip_active=self.cfg.library.skip_active)

        # Optionally, Clean Library
        if self.cfg.library.clean_after_update:
            self.kodi.clean_library()

        # Reapply metadata
        for removed_movie in removed_movies:
            for new_movie in new_movies:
                if removed_movie == new_movie:
                    self.kodi.copy_metadata(removed_movie, new_movie)

        # Update GUIs
        self.kodi.update_guis()

        # Restart playback of previously stopped movie
        for new_movie in new_movies:
            self.kodi.start_playback(new_movie)

        # Skip notifications if disabled
        if not self.cfg.notifications.on_rename:
            self.log.info("Rename Movie notifications disabled. Skipping.")
            return

        # Notify clients
        title = "Radarr - Renamed Movie"
        for movie in new_movies:
            self.kodi.notify(title=title, msg=movie)

    def delete_movie_file(self) -> None:
        """Remove a Movie"""
        self.log.info("Delete Movie File Event Detected")

        # Upgrades only. Stop playback and store data for restart after radarr replaces file
        if self.env.movie_file_delete_reason.lower() == "upgrade":
            # Stop movies that are currently playing
            for old_movie in self.kodi.get_movies_by_file(self.env.movie_file_path):
                self.kodi.stop_playback(old_movie, reason="Processing Upgrade. Please Wait...")
            return

        # Store library data for removed movies and remove those entries
        removed_movies = []
        for old_movie in self.kodi.get_movies_by_file(self.env.movie_file_path):
            self.kodi.stop_playback(old_movie, reason="Deleted Episode")
            if self.kodi.remove_episode(old_movie):
                removed_movies.append(old_movie)

        if not removed_movies:
            self.log.warning("Failed to remove any old movies. Cleaning Required.")
            if not self.cfg.library.clean_after_update:
                self.kodi.clean_library(skip_active=self.cfg.library.skip_active)

        # Optionally, Clean Library
        if self.cfg.library.clean_after_update:
            self.kodi.clean_library(skip_active=self.cfg.library.skip_active)

        # Update remaining guis
        self.kodi.update_guis()

        # Skip notifications if disabled
        if not self.cfg.notifications.on_delete:
            self.log.info("Delete Movie notifications disabled. Skipping.")
            return

        # Notify clients
        title = "Radarr - Deleted Episode"
        for movie in removed_movies:
            self.kodi.notify(title=title, msg=movie)

    def add_movie(self) -> None:
        """Adding a Series"""
        self.log.info("Add Movie Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_movie_add:
            self.log.info("Series Add notifications disabled. Skipping.")
            return

        # Notify clients
        title = "Radarr - Series Added"
        self.kodi.notify(title=title, msg=f"{self.env.movie_title} ({self.env.movie_year})")

    def delete_movie(self) -> None:
        """Deleting a Movie"""
        self.log.info("Movie Delete Event Detected")

        # Edit library only if files were deleted
        if self.env.movie_deleted_files:
            # Stop playback and remove episodes
            movies = self.kodi.get_movies_by_dir(self.env.movie_file_dir)
            for movie in movies:
                self.kodi.stop_playback(movie, "Movie deleted", False)
                self.kodi.remove_movie(movie)

            # Optionally, Clean Library
            if self.cfg.library.clean_after_update:
                self.kodi.clean_library()

            # Update GUIs
            self.kodi.update_guis()
        else:
            self.log.info("No files were deleted. Not editing library or sending notifications.")
            return

        # Skip notifications if disabled
        if not self.cfg.notifications.on_movie_delete:
            self.log.info("Movie Delete notifications disabled. Skipping.")
            return

        # Notify Clients
        title = "Radarr - Movie Deleted"
        self.kodi.notify(title=title, msg=f"{self.env.movie_title} ({self.env.movie_year})")

    def health_issue(self) -> None:
        """Experienced a Health Issue"""
        self.log.info("Health Issue Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_health_issue:
            self.log.info("Health Issue notifications disabled. Skipping.")
            return

        # Notify Clients
        title = "Radarr - Health Issue"
        msg = self.env.health_issue_msg
        self.kodi.notify(title=title, msg=msg)

    def health_restored(self) -> None:
        """Health Restored"""
        self.log.info("Health Restored Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_health_restored:
            self.log.info("Health Restored notifications disabled. Skipping.")
            return

        # Notify Clients
        title = "Radarr - Health Restored"
        msg = f"{self.env.health_restored_msg} Resolved"
        self.kodi.notify(title=title, msg=msg)

    def application_update(self) -> None:
        """Application Updated"""
        self.log.info("Application Update Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_application_update:
            self.log.info("Application Update notifications disabled. Skipping.")
            return

        # Notify Clients
        title = "Radarr - Application Update"
        msg = self.env.update_message
        self.kodi.notify(title=title, msg=msg)

    def manual_interaction_required(self) -> None:
        """Manual Interaction Required"""
        self.log.info("Manual Interaction Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_manual_interaction_required:
            self.log.info("Manual Interaction Required notifications disabled. Skipping.")
            return

        # Notify Clients
        title = "Radarr - Manual Interaction Required"
        msg = f"Radarr needs help with {self.env.movie_title} ({self.env.movie_year})"
        self.kodi.notify(title=title, msg=msg)

    def test(self) -> None:
        """Radarr Tested this script"""
        self.log.info("Test Event Detected")

        # Skip notifications if disabled
        if not self.cfg.notifications.on_test:
            self.log.info("Test notifications disabled. Skipping.")
            return

        # Notify Clients
        title = "Radarr - Testing"
        msg = "Test Passed"
        self.kodi.notify(title=title, msg=msg)
