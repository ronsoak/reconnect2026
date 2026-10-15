from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from website.models import Articles, Logic, Sites


class NewestAdditionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Logic.objects.create(logic_type="CATEGORY", value="Games")
        cls.other_category = Logic.objects.create(logic_type="CATEGORY", value="Cards")
        cls.tag = Logic.objects.create(logic_type="TAG", value="Industry")
        cls.sites = []
        for index in range(12):
            site = Sites.objects.create(
                name=f"Publication {index}", url=f"https://site{index}.example.com",
                rss_feed=f"https://site{index}.example.com/feed",
                category=cls.category, description="Writing", article_count=0,
            )
            cls.sites.append(site)
            Articles.objects.bulk_create([
                Articles(
                    site=site, title=f"Article {index}-{number}",
                    url=f"{site.url}/{number}", image_url="https://example.com/image.jpg",
                    published=timezone.localdate() - timedelta(days=number),
                ) for number in range(15)
            ])
        cls.sites[0].tags.add(cls.tag)
        Sites.objects.filter(pk=cls.sites[0].pk).update(category=cls.other_category)

    def test_ten_newest_public_sites_and_links(self):
        response = self.client.get("/")
        self.assertEqual(
            [site.pk for site in response.context["newest_additions"]],
            [site.pk for site in reversed(self.sites[-10:])],
        )
        self.assertContains(response, 'id="newest-additions-title"', count=1)
        self.assertTemplateUsed(response, "components/newest_additions.html")
        self.assertContains(response, f'href="/publications/{self.sites[-1].pk}/"')

    def test_hidden_empty_and_hidden_article_only_sites_excluded(self):
        Sites.objects.filter(pk=self.sites[-1].pk).update(hidden=True)
        Articles.objects.filter(site=self.sites[-2]).update(hidden=True)
        Articles.objects.filter(site=self.sites[-3]).update(site_hide=True)
        Articles.objects.filter(site=self.sites[-4]).delete()
        response = self.client.get("/")
        self.assertEqual(
            [site.pk for site in response.context["newest_additions"]],
            [site.pk for site in reversed(self.sites[:-4])],
        )

    def test_category_and_focus_filters_and_saved_cookie(self):
        url = f"/?apply=1&category={self.other_category.pk}&tag={self.tag.pk}"
        for path in (url, "/"):
            response = self.client.get(path)
            self.assertEqual(
                [site.pk for site in response.context["newest_additions"]],
                [self.sites[0].pk],
            )

    def test_actual_markup_position_at_both_random_boundaries(self):
        for after in (10, 49):
            with self.subTest(after=after), patch(
                "website.widgets.widget_slots",
                return_value=[{"kind": "newest", "after": after}],
            ):
                response = self.client.get("/")
            html = response.content.decode()
            before_widget = html.split('id="newest-additions-title"')[0]
            self.assertEqual(before_widget.count('class="feed-card__link"'), after)
            self.assertEqual(len(response.context["cards"]), 100)

    def test_exactly_ten_cards_puts_widget_at_end(self):
        keep = list(Articles.objects.order_by("pk").values_list("pk", flat=True)[:10])
        Articles.objects.exclude(pk__in=keep).delete()
        response = self.client.get("/")
        self.assertEqual(response.context["widget_slots"], [{"kind": "newest", "after": 10}])
        self.assertContains(response, "Newest Additions")

    def test_short_and_empty_feeds_omit_widget(self):
        keep = list(Articles.objects.order_by("pk").values_list("pk", flat=True)[:9])
        Articles.objects.exclude(pk__in=keep).delete()
        for empty in (False, True):
            if empty:
                Articles.objects.all().delete()
            response = self.client.get("/")
            self.assertNotContains(response, 'id="newest-additions-title"')

    def test_other_pages_have_no_widget(self):
        for path in ("/newest/", "/popular/", "/search/?q=Article",
                     f"/publications/{self.sites[0].pk}/", "/publications/", "/about/"):
            with self.subTest(path=path):
                self.assertNotContains(self.client.get(path), 'id="newest-additions-title"')
