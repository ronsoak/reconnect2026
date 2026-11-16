"""Bluesky post formatting, session reuse and idempotent publishing."""

import base64
from datetime import datetime, timedelta, timezone as dt_timezone
from io import BytesIO
import json
import re
import secrets
import time
from urllib.parse import urlsplit
import warnings

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
import requests

from website.feed import visible_articles
from website.images import FALLBACK_IMAGE_DIR, fallback_image_url, is_valid_image_url
from website.models import BlueskySession, ScheduledPost, ScheduledPostRun
from website.safe_fetch import UnsafeURL, build_safe_session, fetch


COLLECTION = "app.bsky.feed.post"
API_URL = "https://bsky.social/xrpc/"
RECORD_KEY = re.compile(r"[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}")
# Refresh slightly early so a token cannot expire part-way through a run.
ACCESS_REFRESH_MARGIN = timedelta(minutes=5)
SESSION_ENDPOINTS = ("com.atproto.server.createSession", "com.atproto.server.refreshSession")
# Links must be written in full; trailing sentence punctuation is not part of the link.
LINK_PATTERN = re.compile(r"https?://[^\s<>\"]+")
LINK_TRAILING = ".,;:!?'\")]"
HASHTAG_PATTERN = re.compile(r"(?<!\S)#(\w*[^\W\d_]\w*)")


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
        .filter(
            bluesky=False,
            published__gte=today - timedelta(days=settings.BLUESKY_LOOKBACK_DAYS),
            published__lte=today,
        )
        .filter(Q(site__auto_post=True) | Q(manual_post=True))
        .select_related("site").prefetch_related("site__categories")
        .order_by("published", "created", "pk")
    )


def post_text(article, mention_did=None):
    """Facet offsets are UTF-8 bytes, not Python character offsets."""
    text = f"🟨 Reconnect Recommends:\n\n✍️ By: {article.site.name}"
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
    tags = []
    for category in article.site.categories.all():
        value = category.value.strip()
        if value.casefold() == "geek culture":
            tag = "geek"
        else:
            value = re.sub(r"['\u2019]s$", "", value, flags=re.IGNORECASE)
            tag = "".join(character for character in value.lower() if character.isalnum())
        if not tag or tag.isdecimal():
            raise BlueskyError("Each category must produce a non-numeric hashtag.")
        if len(tag) > 64:
            raise BlueskyError("A category hashtag exceeds Bluesky's 64-character limit.")
        if tag not in tags:
            tags.append(tag)
    if not tags:
        raise BlueskyError("At least one category is required for a Bluesky post.")

    text += "\n\n" + "\n".join(f"#{tag}" for tag in tags)
    # Facet offsets count UTF-8 bytes, including the separators between hashtags.
    cursor = len(text[:text.index("\n\n#") + 2].encode("utf-8"))
    for tag in tags:
        tag_text = f"#{tag}"
        facets.append({
            "index": {
                "byteStart": cursor,
                "byteEnd": cursor + len(tag_text.encode("utf-8")),
            },
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}],
        })
        cursor += len(tag_text.encode("utf-8")) + 1
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


def due_scheduled_posts(now=None):
    """Return (post, date) occurrences that are due now, earliest first.

    Yesterday is checked too, so a late-evening post can still go out just after
    midnight. Occurrences older than BLUESKY_SCHEDULE_GRACE_MINUTES are skipped.
    """
    now = timezone.localtime(now)
    grace = timedelta(minutes=settings.BLUESKY_SCHEDULE_GRACE_MINUTES)
    days = (now.date() - timedelta(days=1), now.date())
    posted = set(
        ScheduledPostRun.objects.filter(date__in=days, posted_at__isnull=False)
        .values_list("scheduled_post_id", "date")
    )
    due = []
    for post in ScheduledPost.objects.filter(active=True):
        for day in days:
            if not post.runs_on(day) or (post.pk, day) in posted:
                continue
            scheduled = timezone.make_aware(datetime.combine(day, post.post_time))
            if scheduled <= now <= scheduled + grace:
                due.append((scheduled, post.pk, post, day))
    due.sort(key=lambda item: item[:2])
    return [(post, day) for _, _, post, day in due]


def scheduled_post_facets(text):
    """Clickable links and hashtags; Bluesky does not detect them server-side."""
    text = (text or "").strip()
    if not text:
        raise BlueskyError("Scheduled post text is empty.")
    if len(text) > 300:
        raise BlueskyError("Scheduled post text exceeds 300 characters.")

    def byte_range(start, end):
        return {"byteStart": len(text[:start].encode("utf-8")), "byteEnd": len(text[:end].encode("utf-8"))}

    facets = []
    for match in LINK_PATTERN.finditer(text):
        link = match.group().rstrip(LINK_TRAILING)
        if not is_valid_image_url(link):
            continue
        facets.append({
            "index": byte_range(match.start(), match.start() + len(link)),
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
        })
    for match in HASHTAG_PATTERN.finditer(text):
        tag = match.group(1)
        if len(tag) <= 64:
            facets.append({
                "index": byte_range(match.start(), match.end()),
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}],
            })
    facets.sort(key=lambda facet: facet["index"]["byteStart"])
    return text, facets


def _cipher():
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"reconnect-bluesky-session",
    ).derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def token_expiry(token):
    """Read a JWT's expiry for scheduling refreshes only; Bluesky still validates it."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(int(claims["exp"]), tz=dt_timezone.utc)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None


class BlueskyClient:
    """Use fixed Bluesky-hosted endpoints; never send credentials to article/image URLs.

    The login is stored encrypted in BlueskySession and reused across runs. An
    expiring access token is refreshed with the refresh token; the app password
    is only used when no usable session exists.
    """

    def __init__(self, identifier, password, warn=None):
        self.identifier = identifier.strip().lstrip("@")
        self.password = password
        self.warn = warn or (lambda message: None)
        self.session = requests.Session()
        self.session.trust_env = False
        self.did = ""
        self.session_source = ""
        try:
            self.authenticate()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.session.close()

    def authenticate(self, force=False):
        """Reuse, refresh or create a session. ``force`` skips the stored access token."""
        with transaction.atomic():
            # The lock stops overlapping runs from rotating the same refresh token.
            stored = BlueskySession.objects.select_for_update().filter(identifier=self.identifier).first()
            tokens = self._load_tokens(stored)
            if tokens and not force:
                expires = token_expiry(tokens["access"])
                if expires and expires - ACCESS_REFRESH_MARGIN > timezone.now():
                    self._use(stored.did, tokens["access"])
                    self.session_source = "reused"
                    return
            self.session.headers.pop("Authorization", None)
            if tokens:
                try:
                    result = self.request(
                        "POST", "com.atproto.server.refreshSession",
                        headers={"Authorization": f"Bearer {tokens['refresh']}"},
                    )
                    self._save(result)
                    self.session_source = "refreshed"
                    return
                except BlueskyError:
                    self.warn("The stored Bluesky session could not be refreshed; signing in again.")
            result = self.request(
                "POST", "com.atproto.server.createSession",
                json={"identifier": self.identifier, "password": self.password},
            )
            self._save(result)
            self.session_source = "created"

    def _load_tokens(self, stored):
        if stored is None:
            return None
        try:
            tokens = json.loads(_cipher().decrypt(stored.tokens.encode("ascii")))
        except (InvalidToken, ValueError, UnicodeError):
            # Usually a changed SECRET_KEY. Signing in again replaces the session.
            self.warn("The stored Bluesky session could not be decrypted; signing in again.")
            return None
        if not isinstance(tokens, dict) or not all(isinstance(tokens.get(key), str) for key in ("access", "refresh")):
            return None
        return tokens

    def _save(self, result):
        did, access, refresh = result.get("did"), result.get("accessJwt"), result.get("refreshJwt")
        if not isinstance(did, str) or not did.startswith("did:") or not isinstance(access, str) or not isinstance(refresh, str):
            raise BlueskyError("Bluesky returned an incomplete session.")
        tokens = _cipher().encrypt(json.dumps({"access": access, "refresh": refresh}).encode("utf-8")).decode("ascii")
        BlueskySession.objects.update_or_create(
            identifier=self.identifier,
            defaults={"did": did, "tokens": tokens, "access_expires": token_expiry(access)},
        )
        # Only one account posts; drop sessions for any previous identifier.
        BlueskySession.objects.exclude(identifier=self.identifier).delete()
        self._use(did, access)

    def _use(self, did, access):
        self.did = did
        self.session.headers["Authorization"] = f"Bearer {access}"

    def request(self, method, endpoint, allow_missing=False, **kwargs):
        response, result = self._send(method, endpoint, **kwargs)
        if endpoint not in SESSION_ENDPOINTS and self._auth_failed(response.status_code, result):
            # The stored access token was revoked or expired early: renew once and retry.
            self.authenticate(force=True)
            response, result = self._send(method, endpoint, **kwargs)
        if allow_missing and response.status_code in (400, 404) and result.get("error") == "RecordNotFound":
            return None
        if not 200 <= response.status_code < 300:
            # Never echo response bodies, credentials, headers or tokens into logs.
            raise BlueskyError(f"Bluesky {endpoint} returned HTTP {response.status_code}.")
        return result

    def _send(self, method, endpoint, **kwargs):
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
        return response, result

    @staticmethod
    def _auth_failed(status, result):
        return status == 401 or (status == 400 and result.get("error") in ("ExpiredToken", "InvalidToken"))

    @staticmethod
    def valid_record_key(rkey, label="Post"):
        if not isinstance(rkey, str) or not RECORD_KEY.fullmatch(rkey):
            raise BlueskyError(f"{label} does not have a valid reserved Bluesky record key.")
        return rkey

    @classmethod
    def record_key(cls, article):
        return cls.valid_record_key(article.bluesky_rkey, "Article")

    def uri_for(self, rkey):
        return f"at://{self.did}/{COLLECTION}/{rkey}"

    def post_uri(self, article):
        return self.uri_for(self.record_key(article))

    def remote_record(self, rkey):
        """The existing record value at this key, or None."""
        result = self.request(
            "GET", "com.atproto.repo.getRecord", allow_missing=True,
            params={"repo": self.did, "collection": COLLECTION, "rkey": rkey},
        )
        return None if result is None else result.get("value", {})

    def existing_post(self, article):
        value = self.remote_record(self.record_key(article))
        if value is None:
            return None
        if value.get("embed", {}).get("external", {}).get("uri") != article.url:
            raise BlueskyError("The article's Bluesky record key is already used for a different URL.")
        return self.post_uri(article)

    def existing_scheduled_post(self, run):
        rkey = self.valid_record_key(run.bluesky_rkey, "Scheduled post")
        value = self.remote_record(rkey)
        if value is None:
            return None
        if value.get("text") != run.text.strip():
            raise BlueskyError("The scheduled post's record key is already used for different text.")
        return self.uri_for(rkey)

    def create_record(self, rkey, record, reconcile):
        try:
            result = self.request(
                "POST", "com.atproto.repo.createRecord",
                json={"repo": self.did, "collection": COLLECTION, "rkey": rkey, "record": record},
            )
        except BlueskyError:
            # Another run or a timed-out request may already have created this exact key.
            existing = reconcile()
            if existing:
                return existing
            raise
        if result.get("uri") != self.uri_for(rkey):
            raise BlueskyError("Bluesky returned an unexpected post URI; rerun to reconcile.")
        return result["uri"]

    @staticmethod
    def now_iso():
        return timezone.now().isoformat().replace("+00:00", "Z")

    def publish_scheduled(self, run):
        existing = self.existing_scheduled_post(run)
        if existing:
            return existing
        text, facets = scheduled_post_facets(run.text)
        record = {"$type": COLLECTION, "text": text, "createdAt": self.now_iso()}
        if facets:
            record["facets"] = facets
        return self.create_record(run.bluesky_rkey, record, lambda: self.existing_scheduled_post(run))

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
            "$type": COLLECTION, "text": text, "facets": facets, "createdAt": self.now_iso(),
            "embed": {
                "$type": "app.bsky.embed.external",
                "external": {
                    "uri": article.url, "title": article.title,
                    "description": f"From {article.site.name}", "thumb": blob,
                },
            },
        }
        return self.create_record(self.record_key(article), record, lambda: self.existing_post(article))
