#!/usr/bin/env python

"""Radarr Kodi Main Interface"""
import logging
import sys
from pathlib import Path
from src import ConfigParser, LibraryManager, EventHandler, ENV, Events, config_log

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "settings.yaml"


def main() -> None:
    """Main Entry Point"""
    cfg_parser = ConfigParser()
    cfg = cfg_parser.get_config(CONFIG_PATH)
    config_log(cfg.logs)
    log = logging.getLogger("Radarr-Kodi")
    if cfg_parser.is_default(cfg):
        log.warning("Default config file detected. Please EDIT %s", CONFIG_PATH)
        sys.exit(0)
    log.info("Starting...")
    kodi = LibraryManager(cfg.hosts, cfg.library.path_mapping)

    # Break if no hosts are available
    if not kodi.hosts:
        log.critical("Unable to modify library. No active Kodi Hosts.")
        kodi.dispose_hosts()
        sys.exit(1)

    event_handler = EventHandler(ENV, cfg, kodi)

    log.debug("========== Environment ==========")
    for k, v in ENV.raw_vars.items():
        log.debug("%s = %s", k, v)
    log.debug("========== Environment ==========")

    if not kodi.hosts:
        log.critical("Unable to modify library. No active Kodi Hosts.")
        kodi.dispose_hosts()
        return

    match ENV.event_type:
        case Events.ON_GRAB:
            event_handler.grab()
        case Events.ON_DOWNLOAD:
            if ENV.is_upgrade:
                event_handler.download_upgrade()
            else:
                event_handler.download_new()
        case Events.ON_RENAME:
            event_handler.rename()
        case Events.ON_MOVIE_FILE_DELETE:
            event_handler.delete_movie_file()
        case Events.ON_MOVIE_ADD:
            event_handler.add_movie()
        case Events.ON_MOVIE_DELETE:
            event_handler.delete_movie()
        case Events.ON_HEALTH_ISSUE:
            event_handler.health_issue()
        case Events.ON_HEALTH_RESTORED:
            event_handler.health_restored()
        case Events.ON_APPLICATION_UPDATE:
            event_handler.application_update()
        case Events.ON_MANUAL_INTERACTION_REQUIRED:
            event_handler.manual_interaction_required()
        case Events.ON_TEST:
            event_handler.test()
        case _:
            log.critical("Event type was unknown or could not be parsed. Exiting")
            kodi.dispose_hosts()
            sys.exit(1)

    log.info("Processing Complete")
    kodi.dispose_hosts()
    sys.exit(0)


if __name__ == "__main__":
    main()
