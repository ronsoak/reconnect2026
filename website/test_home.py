from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from website.models import Adverts, Articles, Logic, Sites


class HomeFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.video = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.cards = Logic.objects.create(logic_type="CATEGORY", value="Card Games")
        cls.small = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        cls.video_site = Sites.objects.create(
            name="Video Site", url="https://video.example.com",
            rss_feed="https://video.example.com/feed", category=cls.video, description="x",
        )
        cls.card_site = Sites.objects.create(
            name="Card Site", url="https://cards.example.com",
            rss_feed="https://cards.example.com/feed", category=cls.cards, description="x",
        )
        today = timezone.localdate()
        for site in (cls.video_site, cls.card_site):
            Articles.objects.bulk_create([
                Articles(
                    title=f"{site.name} article {i}", url=f"{site.url}/{i}",
                    image_url="https://img.example.com/a.jpg", site=site,
                    published=today - timedelta(days=i),
                )
                for i in range(12)
            ])

    def test_home_shows_article_cards_that_open_in_a_new_tab(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "components/article_card.html")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, "Video Site article 0")
        self.assertEqual(len(response.context["cards"]), 24)

    def test_category_filter_limits_the_cards(self):
        response = self.client.get(f"/?category={self.cards.pk}")
        self.assertEqual(len(response.context["cards"]), 12)
        self.assertNotContains(response, "Video Site article")

    def test_invalid_filter_values_are_ignored(self):
        response = self.client.get("/?category=abc&category=%C2%B2&tag=")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["cards"]), 24)

    def test_missing_image_shows_the_placeholder_without_an_img_tag(self):
        Articles.objects.all().update(image_url="")
        response = self.client.get("/")
        self.assertContains(response, "feed-card__image")
        self.assertNotContains(response, "<img")

    def test_empty_state_when_nothing_matches(self):
        Articles.objects.all().delete()
        response = self.client.get("/")
        self.assertContains(response, "No articles match these filters.")

    def test_advert_card_is_rendered_with_its_link(self):
        today = timezone.localdate()
        Adverts.objects.create(
            title="Ad", message="Try this blog", site_name="Blog", site_url="https://blog.example.com",
            start_date=today - timedelta(days=1), end_date=today + timedelta(days=1),
            concurrency=1, advert_size=self.small,
        )
        response = self.client.get("/")
        self.assertTemplateUsed(response, "components/advert_card.html")
        self.assertContains(response, "Try this blog")
        self.assertContains(response, 'href="https://blog.example.com"')


class FilterCookieTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.video = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.cards = Logic.objects.create(logic_type="CATEGORY", value="Card Games")

    def test_applied_filters_are_saved_for_a_year(self):
        response = self.client.get(f"/?apply=1&category={self.video.pk}&category={self.cards.pk}")
        cookie = response.cookies["reconnect_filters"]
        self.assertEqual(cookie["max-age"], 60 * 60 * 24 * 365)
        self.assertIn(f"category={self.video.pk}", cookie.value)

    def test_saved_filters_are_used_when_url_has_none(self):
        self.client.get(f"/?apply=1&category={self.video.pk}")
        response = self.client.get("/")
        self.assertEqual(response.context["selected_categories"], [str(self.video.pk)])

    def test_url_wins_over_cookie(self):
        self.client.get(f"/?apply=1&category={self.video.pk}")
        response = self.client.get(f"/?apply=1&category={self.cards.pk}")
        self.assertEqual(response.context["selected_categories"], [str(self.cards.pk)])

    def test_apply_with_nothing_selected_clears_choices(self):
        self.client.get(f"/?apply=1&category={self.video.pk}")
        response = self.client.get("/?apply=1")
        self.assertEqual(response.context["selected_categories"], [])
        self.assertEqual(self.client.get("/").context["selected_categories"], [])

    def test_reset_clears_cookie_and_redirects(self):
        self.client.get(f"/?apply=1&category={self.video.pk}")
        response = self.client.get("/?reset=1")
        self.assertRedirects(response, "/")
        self.assertEqual(response.cookies["reconnect_filters"].value, "")
        self.assertEqual(self.client.get("/").context["selected_categories"], [])

    def test_junk_cookie_values_are_ignored(self):
        self.client.cookies["reconnect_filters"] = "category=abc&category=%27%3B&tag=9"
        response = self.client.get("/")
        self.assertEqual(response.context["selected_categories"], [])
        self.assertEqual(response.context["selected_tags"], ["9"])

    def test_refresh_button_only_on_dynamic_feed(self):
        self.assertContains(self.client.get("/"), "refresh-button")
        self.assertNotContains(self.client.get("/about/"), "refresh-button")

    def test_filters_also_apply_to_other_pages(self):
        self.client.get(f"/?apply=1&category={self.video.pk}")
        self.assertEqual(self.client.get("/about/").context["selected_categories"], [str(self.video.pk)])
