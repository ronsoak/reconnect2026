from datetime import date
from io import StringIO
from unittest.mock import patch

import requests
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import TestCase

from website.admin import SiteAdmin
from website.models import Articles, Logging, Logic, Sites
from website.safe_fetch import UnsafeURL


def rss(*dates):
    items = "".join(
        f"<item><title>Article</title><link>https://example.com/{index}</link>"
        f"<pubDate>{published}</pubDate></item>"
        for index, published in enumerate(dates)
    )
    return f"<rss version='2.0'><channel><title>Feed</title>{items}</channel></rss>".encode()


class DormantSitesTests(TestCase):
    def setUp(self):
        self.category = Logic.objects.create(logic_type="CATEGORY", value="Games")

    def make_site(self, name="dormant", **kwargs):
        return Sites.objects.create(
            name=name, url=f"https://{name}.example.com",
            rss_feed=f"https://{name}.example.com/feed", category=self.category,
            description="Publication", hidden=True, dormant=True, **kwargs,
        )

    def make_article(self, site, **kwargs):
        return Articles.objects.create(
            site=site, title="Article", url=f"{site.url}/{site.articles_set.count()}",
            image_url="", published=kwargs.pop("published", date(2025, 1, 1)),
            site_hide=True, **kwargs,
        )

    def run_check(self, content=None, **kwargs):
        output, errors = StringIO(), StringIO()
        if content is None:
            content = rss("Thu, 15 Oct 2026 12:00:00 GMT")
        with patch(
            "website.management.commands.check_dormant_sites.fetch",
            return_value=(content, None),
        ) as fetch:
            call_command("check_dormant_sites", stdout=output, stderr=errors, **kwargs)
        return output.getvalue(), errors.getvalue(), fetch

    def test_reactivates_and_syncs_articles_but_preserves_individual_hiding(self):
        site = self.make_site(load_error=True)
        article = self.make_article(site)
        hidden_article = self.make_article(site, hidden=True)
        self.run_check()
        site.refresh_from_db()
        article.refresh_from_db()
        hidden_article.refresh_from_db()
        self.assertFalse(site.hidden)
        self.assertFalse(site.dormant)
        self.assertFalse(site.load_error)
        self.assertFalse(article.site_hide)
        self.assertFalse(hidden_article.site_hide)
        self.assertTrue(hidden_article.hidden)
        self.assertEqual(Articles.objects.count(), 2)
        self.assertTrue(Logging.objects.filter(log_type="DORMANT_CHECK_TASK").exists())
        self.assertTrue(Logging.objects.filter(log_type="HIDE_ARTICLES_TASK").exists())
        self.assertEqual(self.run_check()[2].call_count, 0)

    def test_only_hidden_dormant_sites_are_fetched(self):
        site = self.make_site()
        manual = self.make_site("manual")
        Sites.objects.filter(pk=manual.pk).update(dormant=False)
        active = self.make_site("active")
        Sites.objects.filter(pk=active.pk).update(hidden=False)
        _, _, fetch = self.run_check()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[1], site.rss_feed)
        manual.refresh_from_db()
        self.assertTrue(manual.hidden)

    def test_equal_or_older_feed_dates_do_not_reactivate(self):
        site = self.make_site()
        self.make_article(site)
        self.run_check(rss("Wed, 01 Jan 2025 23:00:00 GMT", "Tue, 31 Dec 2024 12:00:00 GMT"))
        site.refresh_from_db()
        self.assertTrue(site.hidden)
        self.assertTrue(site.dormant)
        self.assertFalse(Logging.objects.filter(log_type="HIDE_ARTICLES_TASK").exists())

    def test_uses_latest_stored_article_including_hidden_articles(self):
        site = self.make_site()
        self.make_article(site)
        self.make_article(site, published=date(2026, 10, 15), hidden=True)
        self.run_check()
        site.refresh_from_db()
        self.assertTrue(site.dormant)

    def test_unsorted_feed_is_scanned_for_newest_date(self):
        site = self.make_site()
        self.make_article(site)
        self.run_check(rss("Tue, 31 Dec 2024 12:00:00 GMT", "Thu, 15 Oct 2026 12:00:00 GMT"))
        site.refresh_from_db()
        self.assertFalse(site.hidden)

    def test_no_dated_stored_articles_accepts_dated_entry(self):
        for has_undated_article in (False, True):
            with self.subTest(has_undated_article=has_undated_article):
                site = self.make_site(f"empty-{has_undated_article}")
                if has_undated_article:
                    self.make_article(site, published=None)
                self.run_check(site=site.pk)
                site.refresh_from_db()
                self.assertFalse(site.hidden)

    def test_undated_empty_and_non_feed_responses_do_not_reactivate(self):
        site = self.make_site()
        for content in (rss(), rss("not a date"), b"<html>Not a feed</html>"):
            with self.subTest(content=content):
                _, errors, _ = self.run_check(content)
                site.refresh_from_db()
                self.assertTrue(site.dormant)
                self.assertIn("no usable dated entries", errors)

    def test_atom_updated_date_is_supported(self):
        site = self.make_site()
        self.make_article(site)
        self.run_check(b"""<feed xmlns="http://www.w3.org/2005/Atom">
            <title>Feed</title><entry><title>New</title><id>https://example.com/new</id>
            <updated>2026-10-15T12:00:00Z</updated></entry></feed>""")
        site.refresh_from_db()
        self.assertFalse(site.hidden)

    def test_dry_run_fetches_but_does_not_write(self):
        site = self.make_site(load_error=True)
        article = self.make_article(site)
        output, _, fetch = self.run_check(dry_run=True)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn("Would reactivate", output)
        site.refresh_from_db()
        article.refresh_from_db()
        self.assertTrue(site.hidden)
        self.assertTrue(site.dormant)
        self.assertTrue(site.load_error)
        self.assertTrue(article.site_hide)
        self.assertFalse(Logging.objects.exists())

    def test_fetch_failures_are_logged_and_do_not_stop_other_sites(self):
        site = self.make_site("broken")
        healthy = self.make_site("healthy")
        for exception in (UnsafeURL("Private address"), requests.Timeout("Timed out")):
            with self.subTest(exception=exception):
                Sites.objects.filter(pk=healthy.pk).update(hidden=True, dormant=True)
                errors = StringIO()
                with patch(
                    "website.management.commands.check_dormant_sites.fetch",
                    side_effect=[exception, (rss("Thu, 15 Oct 2026 12:00:00 GMT"), None)],
                ), self.assertRaises(CommandError):
                    call_command("check_dormant_sites", stdout=StringIO(), stderr=errors)
                site.refresh_from_db()
                healthy.refresh_from_db()
                self.assertTrue(site.dormant)
                self.assertFalse(healthy.dormant)
                self.assertIn("feed check failed", errors.getvalue())
                self.assertTrue(Logging.objects.filter(value__contains=str(exception)).exists())

    def test_limit_and_site_options(self):
        first = self.make_site("first")
        second = self.make_site("second")
        self.assertEqual(self.run_check(limit=1, dry_run=True)[2].call_count, 1)
        _, _, fetch = self.run_check(site=second.pk, dry_run=True)
        self.assertEqual(fetch.call_args.args[1], second.rss_feed)
        first.refresh_from_db()
        self.assertTrue(first.dormant)

    def test_invalid_arguments_do_not_fetch(self):
        for options in ({"limit": -1}, {"request_timeout": 0}, {"request_timeout": float("nan")}):
            with self.subTest(options=options), self.assertRaises(CommandError):
                self.run_check(**options)

    def test_manual_exclusion_during_fetch_prevents_reactivation(self):
        site = self.make_site()

        def exclude(*args, **kwargs):
            Sites.objects.filter(pk=site.pk).update(dormant=False)
            return rss("Thu, 15 Oct 2026 12:00:00 GMT"), None

        with patch("website.management.commands.check_dormant_sites.fetch", side_effect=exclude):
            call_command("check_dormant_sites", stdout=StringIO())
        site.refresh_from_db()
        self.assertTrue(site.hidden)

    def test_sync_failure_rolls_back_reactivation(self):
        site = self.make_site(load_error=True)
        self.make_article(site)
        with patch(
            "website.management.commands.hide_articles.Articles.objects.filter",
            side_effect=DatabaseError("Sync failed"),
        ), self.assertRaises(DatabaseError):
            self.run_check()
        site.refresh_from_db()
        self.assertTrue(site.hidden)
        self.assertTrue(site.dormant)
        self.assertTrue(site.load_error)

    def test_admin_hide_action_excludes_dormant_site_from_recovery(self):
        site = self.make_site()
        SiteAdmin(Sites, AdminSite()).hide_site(None, Sites.objects.filter(pk=site.pk))
        site.refresh_from_db()
        self.assertTrue(site.hidden)
        self.assertFalse(site.dormant)


class HideSitesDormancyTests(TestCase):
    def setUp(self):
        category = Logic.objects.create(logic_type="CATEGORY", value="Games")
        self.site = Sites.objects.create(
            name="Inactive", url="https://example.com", rss_feed="https://example.com/feed",
            category=category, description="Publication", last_article=271,
        )
        self.article = Articles.objects.create(
            site=self.site, title="Old", url="https://example.com/old", image_url="",
        )

    def test_hiding_marks_dormant_and_syncs_articles(self):
        call_command("hide_sites", stdout=StringIO())
        self.site.refresh_from_db()
        self.article.refresh_from_db()
        self.assertTrue(self.site.hidden)
        self.assertTrue(self.site.dormant)
        self.assertTrue(self.article.site_hide)

    def test_existing_manual_hidden_site_is_not_marked_dormant(self):
        Sites.objects.filter(pk=self.site.pk).update(hidden=True)
        call_command("hide_sites", stdout=StringIO())
        self.site.refresh_from_db()
        self.assertFalse(self.site.dormant)

    def test_threshold_is_strict(self):
        Sites.objects.filter(pk=self.site.pk).update(last_article=270)
        call_command("hide_sites", stdout=StringIO())
        self.site.refresh_from_db()
        self.assertFalse(self.site.hidden)

    def test_dry_run_never_writes_even_with_no_candidates(self):
        for days in (270, 365):
            call_command("hide_sites", days=days, dry_run=True, stdout=StringIO())
            self.assertFalse(Logging.objects.exists())
        self.site.refresh_from_db()
        self.assertFalse(self.site.dormant)
        self.assertFalse(self.site.hidden)

    def test_child_failure_rolls_back_site_flags(self):
        with patch(
            "website.management.commands.hide_articles.Command.handle",
            side_effect=DatabaseError("Sync failed"),
        ), self.assertRaises(DatabaseError):
            call_command("hide_sites", stdout=StringIO())
        self.site.refresh_from_db()
        self.assertFalse(self.site.hidden)
        self.assertFalse(self.site.dormant)
