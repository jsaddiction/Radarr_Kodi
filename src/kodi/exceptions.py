"""Kodi JSON-RPC Exceptions"""


class APIError(Exception):
    """Kodi Api Error"""


class ScanTimeout(APIError):
    """Waited too long for library to scan"""
