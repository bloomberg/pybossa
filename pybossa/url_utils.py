# -*- coding: utf8 -*-
"""Helpers for URLs exposed to browsers."""

from urllib.parse import urlparse


def http_url_or_none(value):
    """Return an absolute HTTP(S) URL, or ``None`` for an unsafe value."""
    if not isinstance(value, str):
        return None

    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return None

    if parsed.scheme.lower() not in ('http', 'https') or not hostname:
        return None
    return value
