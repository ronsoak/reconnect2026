from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase

from website.feed import FeedCard
from website.images import clean_image_url, fallback_image_url, is_valid_image_url
from website.models import Articles, Logic, Sites


class ImageAddressTests(SimpleTestCase):
    def test_valid_and_invalid_addresses(self):
        for url in ("https://example.com/a.jpg", "http://example.com/a.jpg"):
            self.assertTrue(is_valid_image_url(url))
        for url in ("", None, "/static/og-image.png", "img/a.png", "//example.com/a.png",
                    "data:image/png;base64,AAAA", "javascript:alert(1)", "https://", "ftp://example.com/a.png"):
            self.assertFalse(is_valid_image_url(url), url)

    def test_clean_image_url(self):
        self.assertEqual(clean_image_url("  https://example.com/a.jpg "), "https://example.com/a.jpg")
        self.assertEqual(clean_image_url("/static/og-image.png"), "")
        self.assertEqual(clean_image_url("https://example.com/" + "a" * 600), "")

    def test_fallback_image_is_stable_and_ignores_unsupported_files(self):
        with TemporaryDirectory() as directory:
            fallback_dir = Path(directory)
            for name in ("a.jpg", "b.png", "c.webp", "ignore.txt"):
                (fallback_dir / name).touch()

            with mock.patch("website.images.FALLBACK_IMAGE_DIR", fallback_dir):
                first = fallback_image_url(4)
                again = fallback_image_url(4)
                self.assertEqual(first, again)
                self.assertEqual(first, "/static/images/article-fallbacks/b.png")

    def test_no_fallback_images_returns_empty_url(self):
        with TemporaryDirectory() as directory:
            with mock.patch("website.images.FALLBACK_IMAGE_DIR", Path(directory)):
                self.assertEqual(fallback_image_url(1), "")


class ImageCardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.site = Sites.objects.create(name="S", url="https://s.example.com", rss_feed="https://s.example.com/f", category=cat, description="x")

    def article(self, image_url, n=1):
        return Articles.objects.create(title=f"T{n}", url=f"https://s.example.com/{n}", site=self.site, image_url=image_url, run_id=1)

    def render(self, article):
        return render_to_string("components/article_card.html", {"card": FeedCard("article", article, "small")})

    def test_card_without_a_valid_image_uses_a_cover_placeholder(self):
        for index, url in enumerate(("", "/static/og-image.png"), start=1):
            html = self.render(self.article(url, index))
            self.assertIn("feed-card--text", html)
            self.assertNotIn("<img", html)
            self.assertIn("feed-card__image--placeholder", html)
            self.assertIn("Cover image unavailable", html)

    def test_card_with_an_image_shows_it(self):
        html = self.render(self.article("https://example.com/a.jpg"))
        self.assertIn("<img", html)
        self.assertNotIn('feed-card--small feed-card--text', html)

    def test_missing_image_uses_fallback_asset_when_available(self):
        article = self.article("", 1)
        with mock.patch("website.feed.fallback_image_url", return_value="/static/images/article-fallbacks/a.jpg"):
            html = self.render(article)
        self.assertIn('src="/static/images/article-fallbacks/a.jpg"', html)
        self.assertIn("feed-card--small feed-card--text", html)
        self.assertNotIn("Cover image unavailable", html)

    def test_check_images_blanks_only_bad_addresses(self):
        good = self.article("https://example.com/a.jpg", 1)
        bad = self.article("/static/og-image.png", 2)
        blank = self.article("", 3)
        call_command("check_images", "--dry-run", stdout=StringIO())
        bad.refresh_from_db()
        self.assertEqual(bad.image_url, "/static/og-image.png")
        call_command("check_images", stdout=StringIO())
        for article in (good, bad, blank):
            article.refresh_from_db()
        self.assertEqual((good.image_url, bad.image_url, blank.image_url), ("https://example.com/a.jpg", "", ""))
        self.assertEqual(Articles.objects.count(), 3)

    def test_check_images_remote_blanks_addresses_that_are_not_images(self):
        good = self.article("https://example.com/a.jpg", 1)
        broken = self.article("https://example.com/missing.jpg", 2)
        with mock.patch("website.management.commands.check_images.remote_image_works", side_effect=lambda url: "missing" not in url):
            call_command("check_images", "--remote", "--workers", "1", stdout=StringIO())
        good.refresh_from_db()
        broken.refresh_from_db()
        self.assertEqual(good.image_url, "https://example.com/a.jpg")
        self.assertEqual(broken.image_url, "")


class FilterMenuTests(TestCase):
    def test_labels_and_select_all(self):
        html = self.client.get("/").content.decode()
        self.assertIn("Category", html)
        self.assertIn("Focus", html)
        self.assertNotIn("Site type", html)
        self.assertNotIn(">Genre", html)
        self.assertIn("js/filters.js", html)
