from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from website.models import Articles, Logic, Sites


class TickerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Logic.objects.create(logic_type="CATEGORY", value="Games")
        cls.other_category = Logic.objects.create(logic_type="CATEGORY", value="Cards")
        cls.focus = Logic.objects.create(logic_type="TAG", value="Industry")
        cls.site = Sites.objects.create(
            name="Publication", url="https://example.com",
            rss_feed="https://example.com/feed", category=cls.category, description="Writing",
        )
        cls.site.tags.add(cls.focus)
        today = timezone.localdate()
        Articles.objects.bulk_create([
            Articles(
                site=cls.site, title=f"Article {index}", url=f"https://example.com/{index}",
                published=today - timedelta(days=index % 8), image_url="",
            ) for index in range(30)
        ])

    def test_ten_unique_recent_articles_and_tracked_links(self):
        response = self.client.get("/")
        articles = response.context["ticker_articles"]
        self.assertEqual(len(articles), 10)
        self.assertEqual(len({article.pk for article in articles}), 10)
        self.assertTemplateUsed(response, "components/article_ticker.html")
        self.assertNotContains(response, "Pause ticker")
        self.assertContains(response, 'class="article-ticker__separator" aria-hidden="true">|</span>', count=10)
        self.assertContains(response, 'aria-label="Recent articles"', count=1)
        self.assertContains(response, 'src="/static/js/ticker.js"')
        for article in articles:
            self.assertContains(response, f'href="/go/{article.pk}/"')

    def test_filters_and_saved_filters_apply(self):
        response = self.client.get(f"/?apply=1&category={self.category.pk}&tag={self.focus.pk}")
        self.assertEqual(len(response.context["ticker_articles"]), 10)
        self.assertEqual(len(self.client.get("/").context["ticker_articles"]), 10)
        response = self.client.get(f"/?apply=1&category={self.other_category.pk}")
        self.assertFalse(response.context["ticker_articles"])
        self.assertNotContains(response, 'aria-label="Recent articles"')

    def test_hidden_undated_future_and_old_articles_excluded(self):
        today = timezone.localdate()
        articles = list(Articles.objects.order_by("pk"))
        Articles.objects.filter(pk=articles[0].pk).update(hidden=True)
        Articles.objects.filter(pk=articles[1].pk).update(site_hide=True)
        Articles.objects.filter(pk=articles[2].pk).update(published=None)
        Articles.objects.filter(pk=articles[3].pk).update(published=today + timedelta(days=1))
        Articles.objects.filter(pk=articles[4].pk).update(published=today - timedelta(days=8))
        selected = {article.pk for article in self.client.get("/").context["ticker_articles"]}
        self.assertTrue(selected.issubset({article.pk for article in articles[5:]}))
        self.assertEqual(len(selected), 10)
        Sites.objects.filter(pk=self.site.pk).update(hidden=True)
        self.assertFalse(self.client.get("/").context["ticker_articles"])

    def test_fewer_than_ten_articles_and_empty_state(self):
        keep = list(Articles.objects.values_list("pk", flat=True)[:3])
        Articles.objects.exclude(pk__in=keep).delete()
        self.assertEqual(len(self.client.get("/").context["ticker_articles"]), 3)
        Articles.objects.all().delete()
        self.assertNotContains(self.client.get("/"), 'aria-label="Recent articles"')

    def test_other_feeds_do_not_include_ticker(self):
        for path in ("/search/?q=Article",
                     "/publications/", f"/publications/{self.site.pk}/", "/about/"):
            with self.subTest(path=path):
                self.assertNotContains(self.client.get(path), 'aria-label="Recent articles"')
