import base64
from datetime import datetime, time, timedelta
from io import BytesIO, StringIO
import json
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
import requests

from website.bluesky import (
    BlueskyClient, BlueskyError, article_thumbnail, due_scheduled_posts, eligible_articles,
    jpeg_thumbnail, new_record_key, post_text, scheduled_post_facets,
)
from website.models import Articles, BlueskySession, Logic, ScheduledPost, ScheduledPostRun, Sites
from website.safe_fetch import UnsafeURL


def jwt(minutes):
    """An unsigned test token that expires ``minutes`` from now."""
    exp = int((timezone.now() + timedelta(minutes=minutes)).timestamp())
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def image_bytes():
    output = BytesIO()
    Image.new("RGBA", (200, 100), (255, 0, 0, 100)).save(output, format="PNG")
    return output.getvalue()


class BlueskyFixtures:
    def setUp(self):
        category = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        self.site = Sites.objects.create(
            name="Example", url="https://example.com",
            rss_feed="https://example.com/feed", description="Writing",
        )
        self.site.categories.add(category)
        self.article = self.make_article()

    def make_article(self, **kwargs):
        return Articles.objects.create(
            site=kwargs.pop("site", self.site), title="Article",
            url=f"https://example.com/{Articles.objects.count()}",
            image_url=kwargs.pop("image_url", ""),
            published=kwargs.pop("published", timezone.localdate()), **kwargs,
        )


class BlueskyTests(BlueskyFixtures, TestCase):
    def test_eligibility_and_oldest_first(self):
        today = timezone.localdate()
        oldest = self.make_article(published=today - timedelta(days=7))
        self.make_article(published=today - timedelta(days=8))
        self.make_article(published=today + timedelta(days=1))
        self.make_article(published=None)
        self.make_article(hidden=True)
        self.make_article(site_hide=True)
        self.make_article(bluesky=True)
        self.assertEqual(list(eligible_articles()), [oldest, self.article])
        self.site.hidden = True
        self.site.save()
        self.assertFalse(eligible_articles().exists())

    def test_blocked_site_allows_manual_override_only(self):
        Sites.objects.filter(pk=self.site.pk).update(auto_post=False)
        self.assertFalse(eligible_articles().exists())
        manual = self.make_article(manual_post=True)
        self.assertEqual(list(eligible_articles()), [manual])
        Sites.objects.filter(pk=self.site.pk).update(hidden=True)
        self.assertFalse(eligible_articles().exists())

    def test_text_and_hashtag(self):
        text, facets = post_text(self.article)
        self.assertEqual(text, "🟨 Reconnect Recommends:\n\n✍️ By: Example\n\n#videogames")
        self.assertEqual(facets[0]["features"][0]["tag"], "videogames")
        for value in ("TCG's", "TCG\u2019s"):
            category, _ = Logic.objects.get_or_create(logic_type="CATEGORY", value=value)
            self.site.categories.set([category])
            self.assertTrue(post_text(self.article)[0].endswith("#tcg"))

    def test_text_uses_all_categories_and_maps_geek_culture(self):
        geek = Logic.objects.create(logic_type="CATEGORY", value="Geek Culture")
        self.site.categories.add(geek)
        text, facets = post_text(self.article)
        self.assertTrue(text.endswith("#geek\n#videogames"))
        self.assertEqual([facet["features"][0]["tag"] for facet in facets], ["geek", "videogames"])

    def test_generated_record_keys_are_valid_tids(self):
        self.assertRegex(new_record_key(), r"^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$")

    def test_mention_offsets_use_utf8_bytes(self):
        self.site.name = "Caf\u00e9 \U0001f3ae"
        self.site.bluesky = "@example.bsky.social"
        text, facets = post_text(self.article, "did:plc:example")
        index = facets[0]["index"]
        self.assertEqual(
            text.encode()[index["byteStart"]:index["byteEnd"]].decode(),
            "@example.bsky.social",
        )
        self.assertEqual(facets[0]["features"][0]["did"], "did:plc:example")
        # The handle stays on the same line as the publication name.
        self.assertIn("✍️ By: Caf\u00e9 \U0001f3ae, @example.bsky.social\n\n#", text)
        tag_index = facets[1]["index"]
        self.assertEqual(text.encode()[tag_index["byteStart"]:tag_index["byteEnd"]].decode(), "#videogames")

    def test_long_post_is_explicit_error(self):
        self.site.name = "x" * 300
        with self.assertRaises(BlueskyError):
            post_text(self.article)

    @override_settings(BLUESKY_IDENTIFIER="", BLUESKY_APP_PASSWORD="")
    def test_dry_run_needs_no_credentials_and_makes_no_network_or_writes(self):
        output = StringIO()
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            call_command("post_bluesky", dry_run=True, stdout=output)
        client.assert_not_called()
        self.article.refresh_from_db()
        self.assertFalse(self.article.bluesky)
        self.assertEqual(self.article.bluesky_rkey, "")
        self.assertIn("Reconnect Recommends", output.getvalue())
        self.assertIn("Local placeholder", output.getvalue())

    @override_settings(BLUESKY_IDENTIFIER="", BLUESKY_APP_PASSWORD="")
    def test_missing_credentials_fail_without_marking_posted(self):
        with self.assertRaisesMessage(CommandError, "Set BLUESKY_IDENTIFIER"):
            call_command("post_bluesky")
        self.article.refresh_from_db()
        self.assertFalse(self.article.bluesky)
        self.assertEqual(self.article.bluesky_rkey, "")

    @override_settings(BLUESKY_IDENTIFIER="example.bsky.social", BLUESKY_APP_PASSWORD="test-only")
    def test_run_posts_exactly_one_and_marks_it_only_on_success(self):
        oldest = self.make_article(published=timezone.localdate() - timedelta(days=2))
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish.return_value = "at://example/post/1"
            call_command("post_bluesky", stdout=StringIO())
            client.return_value.publish.assert_called_once()
            self.assertEqual(client.return_value.publish.call_args.args[0].pk, oldest.pk)
        oldest.refresh_from_db()
        self.article.refresh_from_db()
        self.assertTrue(oldest.bluesky)
        self.assertFalse(self.article.bluesky)

    @override_settings(BLUESKY_IDENTIFIER="example.bsky.social", BLUESKY_APP_PASSWORD="test-only")
    def test_publish_failure_leaves_article_retryable_and_closes_client(self):
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish.side_effect = BlueskyError("Failed")
            with self.assertRaises(CommandError):
                call_command("post_bluesky")
            client.return_value.close.assert_called_once()
        self.article.refresh_from_db()
        self.assertFalse(self.article.bluesky)
        self.assertTrue(self.article.bluesky_rkey)
        reserved_key = self.article.bluesky_rkey
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish.return_value = "at://example/post/1"
            call_command("post_bluesky", stdout=StringIO())
            self.assertEqual(client.return_value.publish.call_args.args[0].bluesky_rkey, reserved_key)

    def test_empty_queue_does_not_login(self):
        Articles.objects.update(bluesky=True)
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            call_command("post_bluesky", stdout=StringIO())
        client.assert_not_called()

    @override_settings(BLUESKY_IDENTIFIER="example.bsky.social", BLUESKY_APP_PASSWORD="test-only")
    def test_database_failure_after_publishing_preserves_reserved_key(self):
        original_save = Articles.save

        def save(instance, *args, **kwargs):
            if kwargs.get("update_fields") == ["bluesky"]:
                raise DatabaseError("Simulated save failure")
            return original_save(instance, *args, **kwargs)

        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish.return_value = "at://example/post/1"
            with patch.object(Articles, "save", save), self.assertRaises(DatabaseError):
                call_command("post_bluesky", stdout=StringIO())
        self.article.refresh_from_db()
        self.assertFalse(self.article.bluesky)
        self.assertTrue(self.article.bluesky_rkey)

    def test_thumbnail_is_jpeg_under_one_megabyte(self):
        content = jpeg_thumbnail(image_bytes())
        self.assertLess(len(content), 1_000_000)
        with Image.open(BytesIO(content)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")

    def test_missing_image_uses_real_local_placeholder_without_network(self):
        warn = Mock()
        with patch("website.bluesky.fetch") as fetch:
            content = article_thumbnail(self.article, warn)
        fetch.assert_not_called()
        warn.assert_called_once()
        self.assertTrue(content.startswith(b"\xff\xd8"))

    def test_broken_unsafe_or_invalid_remote_image_uses_placeholder(self):
        self.article.image_url = "https://example.com/image.png"
        for error in (requests.Timeout(), UnsafeURL("Private address"), None):
            with self.subTest(error=error), patch("website.bluesky.fetch") as fetch:
                if error:
                    fetch.side_effect = error
                else:
                    fetch.return_value = (b"not an image", None)
                warn = Mock()
                content = article_thumbnail(self.article, warn)
                self.assertTrue(content.startswith(b"\xff\xd8"))
                warn.assert_called_once()

    def test_valid_remote_image_uses_guarded_fetch(self):
        self.article.image_url = "https://example.com/image.png"
        warn = Mock()
        with patch("website.bluesky.fetch", return_value=(image_bytes(), None)) as fetch:
            article_thumbnail(self.article, warn)
        self.assertEqual(fetch.call_args.args[1], self.article.image_url)
        warn.assert_not_called()

    def test_missing_placeholder_is_explicit_error(self):
        with patch("website.bluesky.fallback_image_url", return_value=""):
            with self.assertRaisesMessage(BlueskyError, "No local"):
                article_thumbnail(self.article, Mock())


class BlueskyClientTests(BlueskyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.article.bluesky_rkey = new_record_key()
        self.session_patch = patch("website.bluesky.requests.Session")
        self.session = self.session_patch.start().return_value
        self.addCleanup(self.session_patch.stop)
        self.session.request.return_value = self.response({
            "did": "did:plc:account", "accessJwt": jwt(120), "refreshJwt": "test-refresh",
        })
        self.client = BlueskyClient("example.bsky.social", "test-password")

    @staticmethod
    def response(data, status=200):
        return Mock(status_code=status, json=Mock(return_value=data))

    def record(self):
        return {"value": {"embed": {"external": {"uri": self.article.url}}}}

    def test_existing_record_reconciles_without_reposting_or_uploading(self):
        self.session.request.return_value = self.response(self.record())
        before = self.session.request.call_count
        self.assertEqual(self.client.publish(self.article, Mock()), self.client.post_uri(self.article))
        self.assertEqual(self.session.request.call_count, before + 1)

    def test_record_key_collision_fails(self):
        self.session.request.return_value = self.response({
            "value": {"embed": {"external": {"uri": "https://other.example"}}},
        })
        with self.assertRaisesMessage(BlueskyError, "different URL"):
            self.client.publish(self.article, Mock())

    def test_live_payload_has_mention_hashtag_and_rich_link_thumbnail(self):
        self.article.site.bluesky = "example.bsky.social"
        self.session.request.side_effect = [
            self.response({"error": "RecordNotFound"}, 400),
            self.response({"did": "did:plc:publication"}),
            self.response({"blob": {"$type": "blob", "ref": {"$link": "cid"}}}),
            self.response({"uri": self.client.post_uri(self.article)}),
        ]
        with patch("website.bluesky.article_thumbnail", return_value=b"jpeg"):
            self.client.publish(self.article, Mock())
        request = self.session.request.call_args
        payload = request.kwargs["json"]
        self.assertEqual(payload["rkey"], self.article.bluesky_rkey)
        record = payload["record"]
        self.assertEqual(record["embed"]["external"]["uri"], self.article.url)
        self.assertEqual(record["embed"]["external"]["title"], self.article.title)
        self.assertIn("thumb", record["embed"]["external"])
        self.assertEqual(record["facets"][0]["features"][0]["did"], "did:plc:publication")
        self.assertFalse(request.kwargs["allow_redirects"])

    def test_uncertain_create_result_reconciles_same_key(self):
        self.session.request.side_effect = [
            self.response({"error": "RecordNotFound"}, 400),
            self.response({"blob": {"$type": "blob"}}),
            requests.Timeout(),
            self.response(self.record()),
        ]
        with patch("website.bluesky.article_thumbnail", return_value=b"jpeg"):
            self.assertEqual(self.client.publish(self.article, Mock()), self.client.post_uri(self.article))

    def test_failed_create_with_no_remote_record_remains_an_error(self):
        self.session.request.side_effect = [
            self.response({"error": "RecordNotFound"}, 400),
            self.response({"blob": {"$type": "blob"}}),
            requests.Timeout(),
            self.response({"error": "RecordNotFound"}, 400),
        ]
        with patch("website.bluesky.article_thumbnail", return_value=b"jpeg"):
            with self.assertRaisesMessage(BlueskyError, "network error"):
                self.client.publish(self.article, Mock())

    def test_auth_or_server_error_is_not_misread_as_missing_record(self):
        self.session.request.return_value = self.response({"error": "ExpiredToken"}, 401)
        with self.assertRaisesMessage(BlueskyError, "HTTP 401"):
            self.client.existing_post(self.article)

    def endpoints(self, start=0):
        return [call.args[1].rsplit("/", 1)[-1] for call in self.session.request.call_args_list[start:]]

    def test_session_is_stored_encrypted_and_reused_without_signing_in(self):
        stored = BlueskySession.objects.get()
        self.assertEqual(stored.did, "did:plc:account")
        self.assertNotIn("test-refresh", stored.tokens)
        self.assertNotIn(self.session.headers.__setitem__.call_args.args[1].split()[1], stored.tokens)
        before = self.session.request.call_count
        client = BlueskyClient("example.bsky.social", "test-password")
        self.assertEqual(client.session_source, "reused")
        self.assertEqual(self.session.request.call_count, before)

    def test_expiring_access_token_is_refreshed_with_refresh_token(self):
        BlueskySession.objects.all().delete()
        self.session.request.return_value = self.response({
            "did": "did:plc:account", "accessJwt": jwt(2), "refreshJwt": "old-refresh",
        })
        BlueskyClient("example.bsky.social", "test-password")
        before = self.session.request.call_count
        self.session.request.return_value = self.response({
            "did": "did:plc:account", "accessJwt": jwt(120), "refreshJwt": "new-refresh",
        })
        client = BlueskyClient("example.bsky.social", "test-password")
        self.assertEqual(client.session_source, "refreshed")
        self.assertEqual(self.endpoints(before), ["com.atproto.server.refreshSession"])
        call = self.session.request.call_args
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer old-refresh")
        self.assertNotIn("json", call.kwargs)

    def test_failed_refresh_falls_back_to_password_sign_in(self):
        BlueskySession.objects.update(access_expires=None)
        with patch("website.bluesky.token_expiry", return_value=None):
            before = self.session.request.call_count
            self.session.request.side_effect = [
                self.response({"error": "ExpiredToken"}, 400),
                self.response({"did": "did:plc:account", "accessJwt": jwt(120), "refreshJwt": "fresh"}),
            ]
            warn = Mock()
            client = BlueskyClient("example.bsky.social", "test-password", warn)
        self.assertEqual(client.session_source, "created")
        self.assertEqual(self.endpoints(before), [
            "com.atproto.server.refreshSession", "com.atproto.server.createSession",
        ])
        warn.assert_called_once()

    def test_undecryptable_session_signs_in_again(self):
        BlueskySession.objects.update(tokens="not-encrypted")
        before = self.session.request.call_count
        client = BlueskyClient("example.bsky.social", "test-password", Mock())
        self.assertEqual(client.session_source, "created")
        self.assertEqual(self.endpoints(before), ["com.atproto.server.createSession"])

    def test_rejected_access_token_renews_session_and_retries_once(self):
        before = self.session.request.call_count
        self.session.request.side_effect = [
            self.response({"error": "InvalidToken"}, 401),
            self.response({"did": "did:plc:account", "accessJwt": jwt(120), "refreshJwt": "next"}),
            self.response({"error": "RecordNotFound"}, 400),
        ]
        self.assertIsNone(self.client.existing_post(self.article))
        self.assertEqual(self.endpoints(before), [
            "com.atproto.repo.getRecord", "com.atproto.server.refreshSession", "com.atproto.repo.getRecord",
        ])

    def test_scheduled_post_is_plain_text_with_link_and_tag_facets(self):
        post = ScheduledPost.objects.create(name="News", text="Subscribe https://example.com/news. #reconnect", post_time=time(9))
        run = ScheduledPostRun.objects.create(scheduled_post=post, date=timezone.localdate(), text=post.text, bluesky_rkey=new_record_key())
        self.session.request.side_effect = [
            self.response({"error": "RecordNotFound"}, 400),
            self.response({"uri": self.client.uri_for(run.bluesky_rkey)}),
        ]
        self.assertEqual(self.client.publish_scheduled(run), self.client.uri_for(run.bluesky_rkey))
        record = self.session.request.call_args.kwargs["json"]["record"]
        self.assertEqual(record["text"], post.text)
        self.assertNotIn("embed", record)
        self.assertEqual(len(record["facets"]), 2)

    def test_scheduled_record_key_with_different_text_fails(self):
        post = ScheduledPost.objects.create(name="News", text="Subscribe", post_time=time(9))
        run = ScheduledPostRun.objects.create(scheduled_post=post, date=timezone.localdate(), text="Subscribe", bluesky_rkey=new_record_key())
        self.session.request.return_value = self.response({"value": {"text": "Something else"}})
        with self.assertRaisesMessage(BlueskyError, "different text"):
            self.client.publish_scheduled(run)

    def test_errors_do_not_echo_sensitive_response_content(self):
        self.session.request.return_value = self.response({"message": "test-password test-token"}, 400)
        with self.assertRaises(BlueskyError) as raised:
            self.client.existing_post(self.article)
        self.assertNotIn("test-password", str(raised.exception))
        self.assertNotIn("test-token", str(raised.exception))


class ScheduledPostTests(BlueskyFixtures, TestCase):
    def schedule(self, minutes_ago=1, **kwargs):
        moment = timezone.localtime() - timedelta(minutes=minutes_ago)
        kwargs.setdefault("name", "Newsletter")
        kwargs.setdefault("text", "Subscribe: https://example.com/news #newsletter")
        return ScheduledPost.objects.create(post_time=moment.time().replace(microsecond=0), **kwargs)

    def test_facets_use_utf8_bytes_and_exclude_trailing_punctuation(self):
        text, facets = scheduled_post_facets("🎮 Read https://example.com/a?b=1). #Games2026 #2026 x#no")
        spans = [text.encode()[f["index"]["byteStart"]:f["index"]["byteEnd"]].decode() for f in facets]
        self.assertEqual(spans, ["https://example.com/a?b=1", "#Games2026"])
        self.assertEqual(facets[0]["features"][0]["uri"], "https://example.com/a?b=1")
        with self.assertRaises(BlueskyError):
            scheduled_post_facets("x" * 301)

    def test_model_validation_limits_text_and_requires_a_day(self):
        post = ScheduledPost(name="Too long", text="x" * 301, post_time=time(9))
        with self.assertRaises(ValidationError) as raised:
            post.full_clean()
        self.assertIn("text", raised.exception.message_dict)
        post.text = "Fine"
        for day in ScheduledPost.WEEKDAYS:
            setattr(post, day, False)
        with self.assertRaises(ValidationError):
            post.full_clean()
        post.active = False
        post.full_clean()

    @override_settings(BLUESKY_SCHEDULE_GRACE_MINUTES=120)
    def test_due_window_weekdays_and_midnight_carry_over(self):
        now = timezone.make_aware(datetime(2026, 11, 16, 0, 30))  # Monday
        late_sunday = ScheduledPost.objects.create(name="Late", text="a", post_time=time(23, 45))
        ScheduledPost.objects.create(name="Expired", text="b", post_time=time(22, 0))
        ScheduledPost.objects.create(name="Later", text="c", post_time=time(9, 0))
        ScheduledPost.objects.create(name="Inactive", text="d", post_time=time(0, 15), active=False)
        early = ScheduledPost.objects.create(name="Early", text="e", post_time=time(0, 15), monday=False)
        self.assertEqual(due_scheduled_posts(now), [(late_sunday, now.date() - timedelta(days=1))])
        early.monday = True
        early.save()
        self.assertEqual([post.name for post, _ in due_scheduled_posts(now)], ["Late", "Early"])
        ScheduledPostRun.objects.create(
            scheduled_post=late_sunday, date=now.date() - timedelta(days=1), text="a",
            bluesky_rkey=new_record_key(), posted_at=now,
        )
        self.assertEqual([post.name for post, _ in due_scheduled_posts(now)], ["Early"])

    def test_dry_run_previews_scheduled_post_without_writes(self):
        self.schedule()
        output = StringIO()
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            call_command("post_bluesky", dry_run=True, stdout=output)
        client.assert_not_called()
        preview = json.loads(output.getvalue())
        self.assertEqual(preview["links"], ["https://example.com/news"])
        self.assertEqual(preview["hashtags"], ["newsletter"])
        self.assertTrue(preview["article_waiting"])
        self.assertFalse(ScheduledPostRun.objects.exists())

    @override_settings(BLUESKY_IDENTIFIER="example.bsky.social", BLUESKY_APP_PASSWORD="test-only")
    def test_scheduled_post_takes_priority_and_posts_once_per_day(self):
        post = self.schedule()
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.existing_scheduled_post.return_value = None
            client.return_value.publish_scheduled.return_value = "at://example/post/s"
            call_command("post_bluesky", stdout=StringIO())
            client.return_value.publish.assert_not_called()
            run = ScheduledPostRun.objects.get(scheduled_post=post)
            self.assertIsNotNone(run.posted_at)
            self.assertEqual(run.uri, "at://example/post/s")
            client.return_value.publish.return_value = "at://example/post/a"
            call_command("post_bluesky", stdout=StringIO())
            client.return_value.publish_scheduled.assert_called_once()
            client.return_value.publish.assert_called_once()
        self.article.refresh_from_db()
        self.assertTrue(self.article.bluesky)

    @override_settings(BLUESKY_IDENTIFIER="example.bsky.social", BLUESKY_APP_PASSWORD="test-only")
    def test_scheduled_failure_records_error_still_posts_article_and_retries_same_key(self):
        post = self.schedule()
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish_scheduled.side_effect = BlueskyError("Failed")
            client.return_value.publish.return_value = "at://example/post/a"
            with self.assertRaisesMessage(CommandError, "Scheduled post 'Newsletter': Failed"):
                call_command("post_bluesky", stdout=StringIO())
            client.return_value.close.assert_called_once()
        self.article.refresh_from_db()
        self.assertTrue(self.article.bluesky)
        run = ScheduledPostRun.objects.get(scheduled_post=post)
        self.assertEqual(run.error, "Failed")
        self.assertIsNone(run.posted_at)
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish_scheduled.return_value = "at://example/post/s"
            call_command("post_bluesky", stdout=StringIO())
            self.assertEqual(client.return_value.publish_scheduled.call_args.args[0].bluesky_rkey, run.bluesky_rkey)
        run.refresh_from_db()
        self.assertIsNotNone(run.posted_at)
        self.assertEqual(run.error, "")

    @override_settings(BLUESKY_IDENTIFIER="example.bsky.social", BLUESKY_APP_PASSWORD="test-only")
    def test_edited_text_is_used_when_failed_attempt_never_reached_bluesky(self):
        post = self.schedule()
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.publish_scheduled.side_effect = BlueskyError("Failed")
            with self.assertRaises(CommandError):
                call_command("post_bluesky", only="scheduled", stdout=StringIO())
        post.text = "Corrected text"
        post.save()
        with patch("website.management.commands.post_bluesky.BlueskyClient") as client:
            client.return_value.existing_scheduled_post.return_value = None
            client.return_value.publish_scheduled.return_value = "at://example/post/s"
            call_command("post_bluesky", only="scheduled", stdout=StringIO())
            self.assertEqual(client.return_value.publish_scheduled.call_args.args[0].text, "Corrected text")
        self.article.refresh_from_db()
        self.assertFalse(self.article.bluesky)
