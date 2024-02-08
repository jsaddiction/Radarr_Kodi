"""Radarr Environment Variable Parsing"""

from .radarr import RadarrEnvironment, Events

ENV = RadarrEnvironment()

__all__ = [
    "ENV",
    "Events",
]
