import os
import random
import runpy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from website.bluesky import eligible_articles
from website.feed import build_dynamic_feed, pick_popular, pick_random, visible_articles
from website.models import Adverts, Articles, Clicks, Logic, Sites
from website.newsletter import build_newsletter, period_range, render_markdown
from website.rss import ArticlesFeed
from website.widgets import dynamic_widgets, highlight_pool


class EnvironmentValidationTests(SimpleTestCase):
    def test_invalid_environment_values_fail_at_startup(self):
        settings_path = Path(settings.BASE_DIR) / "reconnect/settings.py"
        cases = (
            ("WEB_DYNAMIC_FEED_SIZE", "0"),
            ("API_ORDERED_FEED_PAGE_SIZE", "-1"),
            ("WEB_SEARCH_PAGE_SIZE", "abc"),
            ("PUBLICATION_ARTICLES_LIMIT", ""),
            ("TICKER_LOOKBACK_DAYS", "-1"),
            ("FEED_NEW_PERCENT", "101"),
            ("FEED_RANDOM_PERCENT", "-1"),
            ("API_ANON_THROTTLE_RATE", "0/min"),
            ("API_ANON_THROTTLE_RATE", "120/week"),
            ("API_ANON_THROTTLE_RATE", "unlimited"),
        )
        for name, value in cases:
            with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                with self.assertRaisesMessage(ImproperlyConfigured, name):
                    runpy.run_path(str(settings_path))

    def test_combined_percentages_fail_at_startup(self):
        with patch.dict(os.environ, {"FEED_NEW_PERCENT": "70", "FEED_RANDOM_PERCENT": "40"}):
            with self.assertRaisesMessage(ImproperlyConfigured, "must total at most 100"):
                runpy.run_path(str(Path(settings.BASE_DIR) / "reconnect/settings.py"))

    def test_zero_day_windows_and_percentage_boundaries_are_allowed(self):
        values = {
            "FEED_NEW_PERCENT": "0", "FEED_RANDOM_PERCENT": "100",
            "FEED_RANDOM_MIN_AGE_DAYS": "0", "TICKER_LOOKBACK_DAYS": "0",
            "BLUESKY_LOOKBACK_DAYS": "0", "API_ANON_THROTTLE_RATE": "30/second",
        }
        with patch.dict(os.environ, values):
            loaded = runpy.run_path(str(Path(settings.BASE_DIR) / "reconnect/settings.py"))
        for name, value in values.items():
            self.assertEqual(loaded[name], value if name == "API_ANON_THROTTLE_RATE" else int(value))


class ConfigurableContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.category = Logic.objects.create(logic_type="CATEGORY", value="Games")
        cls.click_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.sites = [
            Sites.objects.create(
                name=f"Site {index}", url=f"https://site{index}.example.com",
                rss_feed=f"https://site{index}.example.com/rss", category=cls.category,
            ) for index in range(3)
        ]
        cls.articles = [
            Articles.objects.create(
                site=cls.sites[index % 3], title=f"Writing {index}",
                url=f"https://example.com/{index}",
                published=cls.today - timedelta(days=index), clicks=60 - index,
            ) for index in range(60)
        ]
        Clicks.objects.bulk_create([
            Clicks(type=cls.click_type, article=str(article.pk), date=cls.today)
            for article in cls.articles
        ])

    def setUp(self):
        cache.clear()

    @override_settings(
        WEB_DYNAMIC_FEED_SIZE=12, API_DYNAMIC_FEED_SIZE=7,
        FEED_NEW_PERCENT=100, FEED_RANDOM_PERCENT=0,
    )
    def test_dynamic_web_and_api_sizes_are_independent(self):
        self.assertEqual(len(self.client.get("/").context["cards"]), 12)
        data = self.client.get("/api/feed/").json()
        self.assertEqual(len(data["cards"]), 7)
        self.assertEqual(set(data), {"feed", "cards"})
        self.assertEqual(len(build_dynamic_feed(feed_size=4)), 4)
        with self.settings(WEB_DYNAMIC_FEED_SIZE=9):
            self.assertEqual(len(build_dynamic_feed()), 9)

    @override_settings(WEB_ORDERED_FEED_PAGE_SIZE=11, API_ORDERED_FEED_PAGE_SIZE=6)
    def test_ordered_web_and_api_sizes_and_page_metadata(self):
        for order in ("newest", "popular"):
            with self.subTest(order=order):
                web = self.client.get(f"/{order}/?page=2")
                self.assertEqual(len(web.context["cards"]), 11)
                self.assertEqual(web.context["page_obj"].number, 2)
                data = self.client.get(f"/api/feed/?feed={order}&page=2").json()
                self.assertEqual(len(data["cards"]), 6)
                self.assertEqual((data["page"], data["num_pages"], data["count"]), (2, 10, 60))
                web_ids = {card.item.pk for card in self.client.get(f"/{order}/").context["cards"]}
                self.assertFalse(web_ids & {card.item.pk for card in web.context["cards"]})

    @override_settings(
        WEB_ORDERED_FEED_PAGE_SIZE=15, API_ORDERED_FEED_PAGE_SIZE=12,
        WEB_DYNAMIC_FEED_SIZE=15, API_DYNAMIC_FEED_SIZE=12,
        FEED_NEW_PERCENT=100, FEED_RANDOM_PERCENT=0,
    )
    def test_custom_feed_sizes_include_adverts_and_preserve_spacing(self):
        size = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        Adverts.objects.create(
            title="Advert", message="Visit", site_url="https://advert.example.com",
            start_date=self.today, end_date=self.today, concurrency=1, advert_size=size,
        )
        for web_url, api_url in (
            ("/", "/api/feed/"), ("/newest/", "/api/feed/?feed=newest"),
            ("/popular/", "/api/feed/?feed=popular"),
        ):
            with self.subTest(web_url=web_url):
                cards = self.client.get(web_url).context["cards"]
                self.assertEqual(len(cards), 15)
                self.assertEqual(sum(card.is_advert for card in cards), 1)
                self.assertTrue(all(not card.is_advert for card in cards[:5]))
                data = self.client.get(api_url).json()["cards"]
                self.assertEqual(len(data), 12)
                self.assertEqual(sum(card["kind"] == "advert" for card in data), 1)
                self.assertTrue(all(card["kind"] == "article" for card in data[:5]))

    @override_settings(WEB_SEARCH_PAGE_SIZE=9, API_SEARCH_PAGE_SIZE=4)
    def test_search_web_and_api_sizes_are_independent(self):
        web = self.client.get("/search/?q=Writing&page=2")
        self.assertEqual(len(web.context["cards"]), 9)
        data = self.client.get("/api/search/?q=Writing&page=2").json()
        self.assertEqual(len(data["cards"]), 4)
        self.assertEqual((data["page"], data["num_pages"], data["count"]), (2, 15, 60))

    @override_settings(PUBLICATIONS_PAGE_SIZE=2, PUBLICATION_ARTICLES_PAGE_SIZE=3, PUBLICATION_ARTICLES_LIMIT=5)
    def test_directory_and_publication_limits(self):
        directory = self.client.get("/publications/").context["page_obj"]
        self.assertEqual((len(directory), directory.paginator.num_pages), (2, 2))
        for order in ("newest", "popular", "random"):
            response = self.client.get(f"/publications/{self.sites[0].pk}/?order={order}&page=2")
            page = response.context["page_obj"]
            self.assertEqual((len(page), page.paginator.count, page.paginator.num_pages), (2, 5, 2))

    @override_settings(RSS_FEED_ITEM_LIMIT=4)
    def test_rss_limit_applies_to_all_and_category_feeds(self):
        feed = ArticlesFeed()
        for category in (None, self.category):
            self.assertEqual(len(feed.items(category)), 4)
        self.assertContains(self.client.get("/about/"), "include up to 4 of the newest articles")
        with self.settings(RSS_FEED_ITEM_LIMIT=2):
            self.assertEqual(len(feed.items()), 2)

    @override_settings(API_ANON_THROTTLE_RATE="2/min")
    def test_api_throttle_reads_the_configured_rate(self):
        self.assertEqual(self.client.get("/api/filters/").status_code, 200)
        self.assertEqual(self.client.get("/api/filters/").status_code, 200)
        self.assertEqual(self.client.get("/api/filters/").status_code, 429)
        self.assertEqual(self.client.get("/").status_code, 200)

    @override_settings(FEED_NEW_PERCENT=0, FEED_RANDOM_PERCENT=0, FEED_POPULAR_POOL_SIZE=4)
    def test_popular_pool_and_remainder(self):
        pool = visible_articles()
        picked = pick_popular(pool, 3, set(), random.Random(1))
        self.assertTrue({a.pk for a in picked}.issubset({a.pk for a in self.articles[:4]}))
        cards = build_dynamic_feed(feed_size=3, rng=random.Random(1))
        self.assertEqual(len(cards), 3)
        self.assertTrue({c.item.pk for c in cards}.issubset({a.pk for a in self.articles[:4]}))
        self.assertEqual(len(pick_popular(pool, 6, set(), random.Random(1))), 6)

    @override_settings(
        FEED_NEW_PERCENT=0, FEED_RANDOM_PERCENT=100, FEED_RANDOM_MIN_AGE_DAYS=20,
    )
    def test_random_age_is_strict_and_configured_percentage_is_used(self):
        picked = pick_random(visible_articles(), 100, set(), self.today, random.Random(1))
        self.assertEqual({a.pk for a in picked}, {a.pk for a in self.articles[21:]})
        cards = build_dynamic_feed(feed_size=8)
        self.assertEqual(len(cards), 8)
        self.assertTrue(all(c.item.published < self.today - timedelta(days=20) for c in cards))

    @override_settings(TICKER_ARTICLE_COUNT=2, TICKER_LOOKBACK_DAYS=3, HIGHLIGHT_POOL_SIZE=4)
    def test_widget_settings_and_filtered_pool(self):
        context = dynamic_widgets([])
        self.assertEqual(len(context["ticker_articles"]), 2)
        self.assertTrue(all(a.published >= self.today - timedelta(days=3) for a in context["ticker_articles"]))
        self.assertEqual(len(highlight_pool()), 4)
        self.assertEqual(len(context["highlight_cards"]), 3)
        with self.settings(TICKER_ARTICLE_COUNT=10, TICKER_LOOKBACK_DAYS=0, HIGHLIGHT_POOL_SIZE=1):
            context = dynamic_widgets([])
            self.assertEqual([a.pk for a in context["ticker_articles"]], [self.articles[0].pk])
            self.assertEqual(len(context["highlight_cards"]), 1)

    @override_settings(NEWSLETTER_WEEKLY_TOP_COUNT=2, NEWSLETTER_MONTHLY_TOP_COUNT=2)
    def test_equal_newsletter_counts_do_not_confuse_periods(self):
        for period in ("week", "month"):
            start, end, top_count = period_range(period, "this", self.today)
            self.assertEqual(top_count, 2)
            data = build_newsletter(start, end, period=period)
            eligible_count = sum(start <= a.published <= end for a in self.articles)
            self.assertEqual(len(data["top"]), min(2, eligible_count))
            self.assertEqual(data["top_count"], 2)
            self.assertIn(f"## Top 2 by clicks this {period}", render_markdown(data))

    @override_settings(BLUESKY_LOOKBACK_DAYS=2)
    def test_bluesky_lookback_is_inclusive_and_zero_means_today(self):
        self.assertEqual(set(eligible_articles().values_list("pk", flat=True)), {a.pk for a in self.articles[:3]})
        with self.settings(BLUESKY_LOOKBACK_DAYS=0):
            self.assertEqual(list(eligible_articles()), [self.articles[0]])
