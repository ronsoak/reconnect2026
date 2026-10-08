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
        self.assertContains(response, 'href="/go/ad/')


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


class OrderedFeedTests(TestCase):
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
        # 120 video articles, article 0 the newest. Article 119 has the most clicks.
        Articles.objects.bulk_create([
            Articles(
                title=f"Video {i}", url=f"https://video.example.com/{i}", image_url="",
                site=cls.video_site, published=today - timedelta(days=i), clicks=i,
            )
            for i in range(120)
        ])
        Articles.objects.create(
            title="Card only", url="https://cards.example.com/1", image_url="",
            site=cls.card_site, published=today - timedelta(days=500),
        )

    def titles(self, response):
        return [c.item.title for c in response.context["cards"] if not c.is_advert]

    def test_newest_is_ordered_by_date_and_paginated(self):
        response = self.client.get("/newest/")
        titles = self.titles(response)
        self.assertEqual(len(titles), 100)
        self.assertEqual(titles[:3], ["Video 0", "Video 1", "Video 2"])
        page_two = self.titles(self.client.get("/newest/?page=2"))
        self.assertEqual(page_two[0], "Video 100")
        self.assertEqual(len(page_two), 21)
        self.assertContains(response, "Page 1 of 2")

    def test_popular_is_ordered_by_rank(self):
        titles = self.titles(self.client.get("/popular/"))
        self.assertEqual(titles[:2], ["Video 119", "Video 118"])

    def test_adverts_take_slots_on_every_page(self):
        today = timezone.localdate()
        Adverts.objects.create(
            title="Ad", message="Try this blog", site_name="Blog", site_url="https://blog.example.com",
            start_date=today - timedelta(days=1), end_date=today + timedelta(days=1),
            concurrency=2, advert_size=self.small,
        )
        cards = self.client.get("/newest/").context["cards"]
        self.assertEqual(len(cards), 100)
        self.assertEqual(sum(c.is_advert for c in cards), 2)
        self.assertTrue(all(not c.is_advert for c in cards[:5]))

    def test_filters_apply_and_tabs_are_linked(self):
        response = self.client.get(f"/newest/?apply=1&category={self.cards.pk}")
        self.assertEqual(self.titles(response), ["Card only"])
        self.assertContains(response, 'href="/popular/"')

    def test_bad_page_numbers_fall_back_safely(self):
        self.assertEqual(self.client.get("/newest/?page=abc").status_code, 200)
        self.assertEqual(self.client.get("/newest/?page=999").status_code, 200)

    def test_reset_stays_on_the_same_page(self):
        self.assertRedirects(self.client.get("/popular/?reset=1"), "/popular/")

    def test_no_refresh_button_on_newest_or_popular(self):
        self.assertNotContains(self.client.get("/newest/"), "refresh-button")
        self.assertNotContains(self.client.get("/popular/"), "refresh-button")


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.site = Sites.objects.create(
            name="Pixel Press", url="https://p.example.com", rss_feed="https://p.example.com/feed",
            category=cat, description="x",
        )
        cls.hidden_site = Sites.objects.create(
            name="Secret Zelda", url="https://s.example.com", rss_feed="https://s.example.com/feed",
            category=cat, description="x", hidden=True,
        )
        today = timezone.localdate()
        make = lambda title, site, days=0, **kw: Articles.objects.create(
            title=title, url=f"https://x.example.com/{title}", image_url="", site=site,
            published=today - timedelta(days=days), **kw)
        cls.both = make("Zelda dragons", cls.site, 5)
        cls.zelda = make("ZELDA review", cls.site, 1)
        cls.dragon = make("Dragons everywhere", cls.site, 0)
        cls.by_site = make("Unrelated", cls.site, 9)
        make("Zelda hidden article", cls.site, 0, hidden=True)
        make("Zelda in hidden site", cls.hidden_site, 0)

    def titles(self, query):
        return [c.item.title for c in self.client.get("/search/", {"q": query}).context["cards"]]

    def test_case_insensitive_partial_term_match_ranked_by_matches(self):
        self.assertEqual(self.titles("zelda dragons"),
                         ["Zelda dragons", "Dragons everywhere", "ZELDA review"])

    def test_matches_site_name(self):
        self.assertIn("Unrelated", self.titles("pixel"))

    def test_hidden_articles_and_sites_excluded(self):
        titles = self.titles("zelda")
        self.assertNotIn("Zelda hidden article", titles)
        self.assertNotIn("Zelda in hidden site", titles)

    def test_filters_do_not_apply(self):
        self.client.get("/?apply=1&category=999")
        self.assertIn("Zelda dragons", self.titles("zelda"))

    def test_empty_query_and_no_results(self):
        self.assertContains(self.client.get("/search/"), "Type something")
        self.assertContains(self.client.get("/search/?q=nothingmatches"), "No articles found")

    def test_results_are_small_cards_without_adverts_or_filter_bar(self):
        response = self.client.get("/search/?q=zelda")
        self.assertTrue(all(c.size == "small" and not c.is_advert for c in response.context["cards"]))
        self.assertNotContains(response, 'name="apply"')

    def test_pagination_keeps_the_search_text(self):
        from website import feed
        cards, page, _ = feed.search_articles("zelda", page=1, page_size=1)
        self.assertEqual(len(cards), 1)
        self.assertEqual(page.paginator.num_pages, 2)
        response = self.client.get("/search/?q=zelda%20dragons&page=1")
        self.assertNotContains(response, "Next</a>")

    def test_odd_input_is_safe(self):
        self.assertEqual(self.client.get("/search/?q=%25_%27%22&page=abc").status_code, 200)
