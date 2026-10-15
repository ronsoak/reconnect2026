import random
from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from website.models import Articles, Clicks, Logic, Sites
from website.widgets import highlight_pool, widget_slots


class WidgetSlotTests(SimpleTestCase):
    def test_spacing_range_randomization_and_short_feeds(self):
        orders = set()
        for count in (0, 3, 9, 10, 19, 20, 29, 30, 50, 100, 250):
            for seed in range(30):
                slots = widget_slots(count, ["newest", "ticker", "highlight"], random.Random(seed))
                orders.add(tuple(slot["kind"] for slot in slots))
                previous = 0
                for index, slot in enumerate(slots):
                    self.assertGreaterEqual(slot["after"] - previous, 10)
                    self.assertLessEqual(slot["after"], count)
                    if slot["kind"] == "newest":
                        self.assertLessEqual(slot["after"] + index, 49)
                    previous = slot["after"]
        self.assertIn(("newest", "ticker", "highlight"), orders)
        self.assertIn(("highlight", "newest", "ticker"), orders)


class HighlightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Logic.objects.create(logic_type="CATEGORY", value="Games")
        cls.other = Logic.objects.create(logic_type="CATEGORY", value="Cards")
        cls.focus = Logic.objects.create(logic_type="TAG", value="Industry")
        cls.click_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.rss_type = Logic.objects.create(logic_type="CLICK_TYPE", value="RSS")
        cls.advert_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Advert")
        cls.site = Sites.objects.create(
            name="Publication", url="https://example.com",
            rss_feed="https://example.com/rss", category=cls.category,
        )
        cls.site.tags.add(cls.focus)
        cls.today = timezone.localdate()
        cls.articles = [
            Articles.objects.create(
                title=f"Highlight {index}", site=cls.site, url=f"https://example.com/{index}",
                published=cls.today - timedelta(days=400), boost=1000 - index,
            ) for index in range(60)
        ]
        Clicks.objects.bulk_create([
            Clicks(type=cls.click_type, article=str(article.pk), site=cls.site, date=cls.today)
            for index, article in enumerate(cls.articles) for _ in range(index + 1)
        ])

    def test_top_fifty_by_month_clicks_not_rank_or_publication_date(self):
        pool = list(highlight_pool())
        self.assertEqual([a.pk for a in pool], [a.pk for a in reversed(self.articles[10:])])
        self.assertEqual(pool[0].month_clicks, 60)
        Clicks.objects.create(
            type=self.rss_type, article=str(self.articles[-1].pk), date=self.today,
        )
        self.assertEqual(list(highlight_pool())[0].month_clicks, 61)

    def test_click_window_type_visibility_and_filters(self):
        article = self.articles[-1]
        Clicks.objects.create(type=self.advert_type, article=str(article.pk), date=self.today)
        Clicks.objects.create(
            type=self.click_type, article=str(article.pk),
            date=self.today.replace(day=1) - timedelta(days=1),
        )
        Clicks.objects.create(
            type=self.click_type, article=str(article.pk), date=self.today + timedelta(days=1),
        )
        self.assertEqual(list(highlight_pool())[0].month_clicks, 60)
        self.assertEqual(len(highlight_pool([self.category.pk], [self.focus.pk])), 50)
        self.assertFalse(highlight_pool([self.other.pk]))
        for field in ("hidden", "site_hide"):
            Articles.objects.filter(pk=article.pk).update(**{field: True})
            self.assertNotIn(article.pk, [a.pk for a in highlight_pool()])
            Articles.objects.filter(pk=article.pk).update(**{field: False})
        Sites.objects.filter(pk=self.site.pk).update(hidden=True)
        self.assertFalse(highlight_pool())

    def test_rendered_three_unique_tracked_cards_and_other_page_exclusion(self):
        response = self.client.get("/")
        cards = response.context["highlight_cards"]
        self.assertEqual(len({card.item.pk for card in cards}), 3)
        self.assertContains(response, 'id="highlight-reel-title"', count=1)
        self.assertContains(response, 'src="/static/js/feed_widgets.js"')
        self.assertContains(response, 'class="highlight-reel__item"', count=3)
        self.assertNotContains(response, 'aria-roledescription="carousel"')
        self.assertNotContains(response, 'src="/static/js/highlight_reel.js"')
        self.assertNotContains(response, 'aria-label="Next highlight"')
        for card in cards:
            self.assertContains(response, f'href="/go/{card.item.pk}/"')
        for path in ("/search/?q=Highlight",):
            self.assertNotContains(self.client.get(path), 'id="highlight-reel-title"')

    def test_no_clicks_omits_reel_and_small_pool_uses_available_articles(self):
        Clicks.objects.exclude(article=str(self.articles[0].pk)).delete()
        self.assertEqual(len(self.client.get("/").context["highlight_cards"]), 1)
        Clicks.objects.all().delete()
        response = self.client.get("/")
        self.assertFalse(response.context["highlight_cards"])
        self.assertNotContains(response, 'id="highlight-reel-title"')
