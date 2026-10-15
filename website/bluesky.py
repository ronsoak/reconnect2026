"""Bluesky article formatting, thumbnail preparation and idempotent publishing."""

from datetime import timedelta
from io import BytesIO
import re
import secrets
import time
from urllib.parse import urlsplit
import warnings

from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
import requests

from website.feed import visible_articles
from website.images import FALLBACK_IMAGE_DIR, fallback_image_url, is_valid_image_url
from website.safe_fetch import UnsafeURL, build_safe_session, fetch


COLLECTION = "app.bsky.feed.post"
API_URL = "https://bsky.social/xrpc/"


class BlueskyError(Exception):
    """A publishing error safe to display without exposing credentials."""


def new_record_key():
    """AT Protocol TID: 53 timestamp bits and 10 clock-ID bits, sorted base32."""
    number = ((time.time_ns() // 1000) << 10) | secrets.randbelow(1024)
    alphabet = "234567abcdefghijklmnopqrstuvwxyz"
    characters = []
    for _ in range(13):
        characters.append(alphabet[number & 31])
        number >>= 5
    return "".join(reversed(characters))


def eligible_articles():
    today = timezone.localdate()
    return (
        visible_articles()
        .filter(bluesky=False, published__gte=today - timedelta(days=7), published__lte=today)
        .filter(Q(site__auto_post=True) | Q(manual_post=True))
        .select_related("site", "site__category")
        .order_by("published", "created", "pk")
    )


def post_text(article, mention_did=None):
    """Facet offsets are UTF-8 bytes, not Python character offsets."""
    text = f"🟨 Reconnect Recommends:\n\n✍️ By: {article.site.name}\n"
    facets = []
    handle = article.site.bluesky.strip().lstrip("@")
    if handle:
        start = len((text + ", ").encode("utf-8"))
        text += f", @{handle}"
        if mention_did:
            facets.append({
                "index": {"byteStart": start, "byteEnd": len(text.encode("utf-8"))},
                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": mention_did}],
            })
    category = re.sub(r"['\u2019]s$", "", article.site.category.value.strip(), flags=re.IGNORECASE)
    tag = "".join(character for character in category.lower() if character.isalnum())
    if not tag or tag.isdecimal():
        raise BlueskyError("The category must produce a non-numeric hashtag.")
    if len(tag) > 64:
        raise BlueskyError("The category hashtag exceeds Bluesky's 64-character limit.")
    start = len((text + "\n").encode("utf-8"))
    text += f"\n#{tag}"
    facets.append({
        "index": {"byteStart": start, "byteEnd": len(text.encode("utf-8"))},
        "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}],
    })
    # Counting codepoints is conservative: never silently shorten a publication's name.
    if len(text) > 300 or len(text.encode("utf-8")) > 3000:
        raise BlueskyError("Post text is too long; shorten the publication name or category.")
    return text, facets


def jpeg_thumbnail(content):
    """Flatten the first frame and resize/compress below the external-card blob limit."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(content)) as source:
            if source.width * source.height > 20_000_000:
                raise BlueskyError("Image exceeds the thumbnail processing pixel limit.")
            source.thumbnail((1600, 1600))
            image = ImageOps.exif_transpose(source).convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            for quality in (85, 70, 50):
                output = BytesIO()
                background.save(output, format="JPEG", quality=quality)
                if output.tell() < 1_000_000:
                    return output.getvalue()
    raise BlueskyError("Thumbnail could not be compressed below 1 MB.")


def article_thumbnail(article, warn):
    image_errors = (
        OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError,
        Image.DecompressionBombWarning, BlueskyError,
    )
    if is_valid_image_url(article.image_url):
        try:
            with build_safe_session(retries=0, user_agent="reconnect-bluesky/1.0") as session:
                content, _ = fetch(session, article.image_url, timeout=10)
            return jpeg_thumbnail(content)
        except (UnsafeURL, requests.RequestException, *image_errors):
            warn(f"Article {article.pk}: image download/processing failed; using a local placeholder.")
    else:
        warn(f"Article {article.pk}: no usable image; using a local placeholder.")

    fallback = fallback_image_url(article.pk)
    if not fallback:
        raise BlueskyError("No local article placeholder images are available.")
    path = FALLBACK_IMAGE_DIR / urlsplit(fallback).path.rsplit("/", 1)[-1]
    try:
        return jpeg_thumbnail(path.read_bytes())
    except image_errors as exc:
        raise BlueskyError(f"Could not prepare local placeholder {path.name}.") from exc


class BlueskyClient:
    """Use fixed Bluesky-hosted endpoints; never send credentials to article/image URLs."""

    def __init__(self, identifier, password):
        self.session = requests.Session()
        self.session.trust_env = False
        self.did = ""
        try:
            result = self.request(
                "POST", "com.atproto.server.createSession",
                json={"identifier": identifier, "password": password},
            )
            self.did = result["did"]
            token = result["accessJwt"]
            if not isinstance(self.did, str) or not self.did.startswith("did:") or not isinstance(token, str):
                raise BlueskyError("Bluesky returned an invalid session.")
            self.session.headers["Authorization"] = f"Bearer {token}"
        except (KeyError, TypeError) as exc:
            self.close()
            raise BlueskyError("Bluesky returned an incomplete session.") from exc
        except BlueskyError:
            self.close()
            raise

    def close(self):
        self.session.close()

    def request(self, method, endpoint, allow_missing=False, **kwargs):
        try:
            response = self.session.request(
                method, API_URL + endpoint, timeout=20, allow_redirects=False, **kwargs,
            )
        except requests.RequestException:
            raise BlueskyError(f"Bluesky {endpoint} failed due to a network error.") from None
        try:
            result = response.json()
        except ValueError:
            raise BlueskyError(f"Bluesky {endpoint} returned a non-JSON response.") from None
        if not isinstance(result, dict):
            raise BlueskyError(f"Bluesky {endpoint} returned an invalid response.")
        if allow_missing and response.status_code in (400, 404) and result.get("error") == "RecordNotFound":
            return None
        if not 200 <= response.status_code < 300:
            # Never echo response bodies, credentials, headers or tokens into logs.
            raise BlueskyError(f"Bluesky {endpoint} returned HTTP {response.status_code}.")
        return result

    def existing_post(self, article):
        result = self.request(
            "GET", "com.atproto.repo.getRecord", allow_missing=True,
            params={"repo": self.did, "collection": COLLECTION, "rkey": self.record_key(article)},
        )
        if result is None:
            return None
        value = result.get("value", {})
        if value.get("embed", {}).get("external", {}).get("uri") != article.url:
            raise BlueskyError("The article's Bluesky record key is already used for a different URL.")
        return self.post_uri(article)

    @staticmethod
    def record_key(article):
        if not re.fullmatch(r"[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}", article.bluesky_rkey):
            raise BlueskyError("Article does not have a valid reserved Bluesky record key.")
        return article.bluesky_rkey

    def post_uri(self, article):
        return f"at://{self.did}/{COLLECTION}/{self.record_key(article)}"

    def publish(self, article, warn):
        existing = self.existing_post(article)
        if existing:
            return existing
        if not is_valid_image_url(article.url):
            raise BlueskyError("Article link must be an absolute HTTP(S) URL.")
        did = None
        handle = article.site.bluesky.strip().lstrip("@")
        if handle:
            result = self.request("GET", "com.atproto.identity.resolveHandle", params={"handle": handle})
            did = result.get("did")
            if not isinstance(did, str) or not did.startswith("did:"):
                raise BlueskyError("Could not resolve the publication's Bluesky handle.")
        text, facets = post_text(article, did)
        thumbnail = article_thumbnail(article, warn)
        result = self.request(
            "POST", "com.atproto.repo.uploadBlob",
            data=thumbnail, headers={"Content-Type": "image/jpeg"},
        )
        blob = result.get("blob")
        if not isinstance(blob, dict) or blob.get("$type") != "blob":
            raise BlueskyError("Bluesky did not return an uploaded thumbnail blob.")
        record = {
            "$type": COLLECTION, "text": text, "facets": facets,
            "createdAt": timezone.now().isoformat().replace("+00:00", "Z"),
            "embed": {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": article.url, "title": article.title,
                    "description": f"From {article.site.name}", "thumb": blob,
                },
            },
        }
        try:
            result = self.request(
                "POST", "com.atproto.repo.createRecord",
                json={
                    "repo": self.did, "collection": COLLECTION,
                    "rkey": self.record_key(article), "record": record,
                },
            )
        except BlueskyError:
            # Another run or a timed-out request may already have created this exact key.
            existing = self.existing_post(article)
            if existing:
                return existing
            raise
        if result.get("uri") != self.post_uri(article):
            raise BlueskyError("Bluesky returned an unexpected post URI; rerun to reconcile.")
        return result["uri"]
