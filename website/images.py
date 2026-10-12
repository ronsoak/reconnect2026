"""
Checks for article image addresses.

An address is only usable when it is a full http(s) URL with a hostname. Relative paths
such as '/static/og-image.png' can't load from another site's page, so they count as
"no image" and the card is shown as a text card instead.

Examples:
    from website.images import is_valid_image_url
    is_valid_image_url("https://example.com/cover.jpg")   # True
    is_valid_image_url("/static/og-image.png")            # False
"""
from urllib.parse import urlsplit


def is_valid_image_url(url):
    """True for an absolute http(s) address with a hostname."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return False
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname)


def clean_image_url(url, max_length=512):
    """The address trimmed and shortened to fit, or "" when it isn't usable."""
    url = (url or "").strip()
    if not is_valid_image_url(url) or len(url) > max_length:
        return ""
    return url
