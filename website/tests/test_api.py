from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from website.models import Adverts, Articles, Logic, Sites


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.video = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.cards = Logic.objects.create(logic_type="CATEGORY", value="Card Games")
        cls.news = Logic.objects.create(logic_type="TAG", value="News")
        cls.small = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        cls.video_site = Sites.objects.create(
            name="Video Site", url="https://v.example.com", rss_feed="https://v.example.com/feed",
            category=cls.video, description="x",
        )
        cls.card_site = Sites.objects.create(
            name="Card Site", url="https://c.example.com", rss_feed="https://c.example.com/feed",
            category=cls.cards, description="x",
        )
        today = timezone.localdate()
        for site in (cls.video_site, cls.card_site):
            Articles.objects.bulk_create([
                Articles(title=f"{site.name} {i}", url=f"{site.url}/{i}", image_url="", site=site,
                         published=today - timedelta(days=i), clicks=i)
                for i in range(15)
            ])

    def setUp(self):
        cache.clear()

    def test_feed_defaults_to_dynamic_and_hides_internal_fields(self):
        data = self.client.get("/api/feed/").json()
        self.assertEqual(data["feed"], "dynamic")
        card = data["cards"][0]
        self.assertEqual(set(card), {"kind", "size", "item"})
        self.assertEqual(
            set(card["item"]),
            {"id", "title", "url", "image_url", "published", "site", "site_id", "category"},
        )

    def test_multiple_categories_are_an_or(self):
        url = f"/api/feed/?feed=newest&category={self.video.pk}&category={self.cards.pk}"
        self.assertEqual(self.client.get(url).json()["count"], 30)
        url = f"/api/feed/?feed=newest&category={self.cards.pk}"
        self.assertEqual(self.client.get(url).json()["count"], 15)

    def test_newest_and_popular_are_ordered_and_paginated(self):
        newest = self.client.get("/api/feed/?feed=newest").json()
        self.assertEqual(newest["page"], 1)
        self.assertEqual(newest["cards"][0]["item"]["published"], str(timezone.localdate()))
        popular = self.client.get("/api/feed/?feed=popular&page=999").json()
        self.assertEqual(popular["page"], popular["num_pages"])

    def test_adverts_have_their_own_shape(self):
        today = timezone.localdate()
        Adverts.objects.create(
            title="Ad", message="Try this", site_name="Blog", site_url="https://b.example.com",
            start_date=today, end_date=today, concurrency=1, advert_size=self.small,
        )
        cards = self.client.get("/api/feed/?feed=newest").json()["cards"]
        advert = next(c for c in cards if c["kind"] == "advert")
        self.assertEqual(set(advert["item"]), {"id", "message", "site_name", "site_url", "image"})

    def test_bad_feed_and_junk_ids(self):
        self.assertEqual(self.client.get("/api/feed/?feed=nope").status_code, 400)
        self.assertEqual(self.client.get("/api/feed/?category=abc&tag=%27").status_code, 200)

    def test_search(self):
        data = self.client.get("/api/search/?q=card").json()
        self.assertEqual(data["count"], 15)
        self.assertTrue(all(c["kind"] == "article" and c["size"] == "small" for c in data["cards"]))
        self.assertEqual(self.client.get("/api/search/").json()["cards"], [])

    def test_filters_lists_options(self):
        data = self.client.get("/api/filters/").json()
        self.assertEqual({c["value"] for c in data["categories"]}, {"Video Games", "Card Games"})
        self.assertEqual([t["value"] for t in data["tags"]], ["News"])

    def test_read_only_and_no_cookie_filters(self):
        self.assertEqual(self.client.post("/api/feed/").status_code, 405)
        self.client.cookies["reconnect_filters"] = f"category={self.cards.pk}"
        self.assertEqual(self.client.get("/api/feed/?feed=newest").json()["count"], 30)
