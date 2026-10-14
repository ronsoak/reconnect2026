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
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from django.templatetags.static import static


FALLBACK_IMAGE_DIR = Path(__file__).resolve().parent.parent / "static/images/article-fallbacks"
FALLBACK_IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}


@lru_cache(maxsize=8)
def _fallback_image_names(directory, modified_at):
    path = Path(directory)
    return tuple(
        sorted(
            image.name
            for image in path.iterdir()
            if image.is_file() and image.suffix.lower() in FALLBACK_IMAGE_EXTENSIONS
        )
    )


def fallback_image_url(article_id):
    """Return a stable local fallback URL for an article, or an empty string if none exist."""
    try:
        modified_at = FALLBACK_IMAGE_DIR.stat().st_mtime_ns
    except FileNotFoundError:
        return ""

    images = _fallback_image_names(str(FALLBACK_IMAGE_DIR), modified_at)
    if not images:
        return ""

    image_name = images[article_id % len(images)]
    return static(f"images/article-fallbacks/{image_name}")


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
