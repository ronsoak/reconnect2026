from datetime import date, timedelta
from html import unescape
import re
from unittest.mock import patch
from urllib.parse import parse_qs

from django.conf import settings
from django.test import TestCase, override_settings

from website.models import Adverts, Articles, Logic, Sites


class PublicationsDirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.video_games = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.tabletop = Logic.objects.create(logic_type="CATEGORY", value="Tabletop")
        cls.news = Logic.objects.create(logic_type="TAG", value="News")
        cls.reviews = Logic.objects.create(logic_type="TAG", value="Reviews")
        cls.site_type = Logic.objects.create(logic_type="SITE_TYPE", value="Website")
        cls.advert_size = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")

        cls.alpha_site = cls.make_site(
            "Alpha Games", "https://alpha.example.com", cls.video_games, [cls.news]
        )
        cls.zulu_site = cls.make_site(
            "Zulu Tabletop", "https://zulu.example.com", cls.tabletop, [cls.reviews]
        )
        cls.make_article(cls.alpha_site, "Alpha recent", published=date.today())
        cls.make_article(
            cls.alpha_site,
            "Alpha older",
            published=date.today() - timedelta(days=1),
        )
        cls.make_article(cls.zulu_site, "Zulu article", published=date.today())

        cls.hidden_site = cls.make_site(
            "Hidden Site", "https://hidden.example.com", cls.video_games, [cls.news], hidden=True
        )
        cls.make_article(cls.hidden_site, "Hidden-site article")

        no_visible_articles = cls.make_site(
            "No Articles", "https://empty.example.com", cls.video_games, [cls.news]
        )
        cls.make_article(no_visible_articles, "Hidden article", hidden=True)

    @classmethod
    def make_site(cls, name, url, category, tags, hidden=False):
        site = Sites.objects.create(
            name=name,
            url=url,
            rss_feed=f"{url}/feed",
            site_type=cls.site_type,
            description=f"About {name}",
            hidden=hidden,
        )
        site.categories.add(category)
        site.tags.set(tags)
        return site

    @classmethod
    def make_article(cls, site, title, **values):
        values.setdefault("published", date.today())
        return Articles.objects.create(
            title=title,
            url=f"{site.url}/{title.lower().replace(' ', '-')}",
            image_url="",
            site=site,
            **values,
        )

    def pagination_href(self, response, direction):
        match = re.search(
            rf'class="pagination-{direction}" href="([^"]+)"',
            response.content.decode(),
        )
        self.assertIsNotNone(match)
        return unescape(match[1])

    def test_directory_lists_only_visible_sites_with_visible_articles(self):
        response = self.client.get("/publications/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 publications")
        self.assertNotContains(response, "visible")
        self.assertEqual(
            {site.name for site in response.context["page_obj"]},
            {"Alpha Games", "Zulu Tabletop"},
        )
        self.assertEqual(
            next(site for site in response.context["page_obj"] if site.pk == self.alpha_site.pk).visible_article_count,
            2,
        )
        self.assertNotContains(response, "Hidden Site")
        self.assertNotContains(response, "No Articles")
        self.assertContains(response, "Source RSS")
        self.assertContains(response, "2 articles")
        self.assertNotContains(response, "2 visible articles")
        self.assertContains(response, "See articles")

    def test_category_and_focus_filters_can_be_combined(self):
        response = self.client.get(
            f"/publications/?category={self.tabletop.pk}&tag={self.reviews.pk}"
        )

        self.assertEqual(
            [site.pk for site in response.context["page_obj"]],
            [self.zulu_site.pk],
        )

    def test_publication_matches_each_assigned_category(self):
        self.alpha_site.categories.add(self.tabletop)
        response = self.client.get(f"/publications/?category={self.tabletop.pk}")
        self.assertEqual(
            {site.pk for site in response.context["page_obj"]},
            {self.alpha_site.pk, self.zulu_site.pk},
        )

    def test_sort_options_are_supported(self):
        alphabetical = self.client.get("/publications/?sort=alpha")
        reverse_alpha = self.client.get("/publications/?sort=reverse")
        newest = self.client.get("/publications/?sort=newest")
        invalid = self.client.get("/publications/?sort=unknown")

        self.assertEqual(
            [site.name for site in reverse_alpha.context["page_obj"]],
            ["Zulu Tabletop", "Alpha Games"],
        )
        self.assertEqual(
            [site.pk for site in newest.context["page_obj"]],
            [self.zulu_site.pk, self.alpha_site.pk],
        )
        self.assertEqual(
            [site.name for site in alphabetical.context["page_obj"]],
            ["Alpha Games", "Zulu Tabletop"],
        )
        self.assertEqual(invalid.context["sort"], "random")

    def test_directory_defaults_to_random_order(self):
        response = self.client.get("/publications/")
        self.assertEqual(response.context["sort"], "random")
        seed = parse_qs(response.context["extra_query"].lstrip("&"))["seed"][0]
        self.assertRegex(seed, r"^[0-9a-f]{32}$")
        self.assertContains(response, '<option value="random" selected>Random order</option>', html=True)

    @override_settings(PUBLICATIONS_PAGE_SIZE=2)
    def test_random_directory_pagination_preserves_order_filters_and_fresh_visits(self):
        expected = {self.alpha_site.pk}
        self.alpha_site.categories.add(self.tabletop)
        for index in range(5):
            site = self.make_site(
                f"Random site {index}", f"https://random-{index}.example.com",
                self.video_games, [self.news],
            )
            self.make_article(site, f"Random article {index}")
            expected.add(site.pk)

        url = (
            f"/publications/?sort=random&category={self.video_games.pk}"
            f"&category={self.tabletop.pk}&tag={self.news.pk}"
        )
        with patch("website.views.secrets.token_hex", side_effect=["a" * 32, "b" * 32]) as token:
            first = self.client.get(url)
            first_ids = [site.pk for site in first.context["page_obj"]]
            ordering = list(first.context["page_obj"].paginator.object_list.values_list("pk", flat=True))
            seen = first_ids[:]
            response = first
            while response.context["page_obj"].has_next():
                href = self.pagination_href(response, "next")
                params = parse_qs(href.split("?", 1)[1])
                self.assertEqual(params["seed"], ["a" * 32])
                self.assertEqual(params["category"], [str(self.video_games.pk), str(self.tabletop.pk)])
                self.assertEqual(params["tag"], [str(self.news.pk)])
                self.assertEqual(params["sort"], ["random"])
                response = self.client_class().get("/publications/" + href)
                seen.extend(site.pk for site in response.context["page_obj"])
                if response.context["page_obj"].number == 2:
                    previous = self.client.get("/publications/" + self.pagination_href(response, "previous"))
                    self.assertEqual([site.pk for site in previous.context["page_obj"]], first_ids)
            self.assertEqual(seen, ordering)
            self.assertEqual(set(seen), expected)
            self.assertEqual(len(seen), len(expected))

            fresh = self.client.get(url)
            self.assertIn("seed=" + "b" * 32, fresh.context["extra_query"])
            fresh_order = list(fresh.context["page_obj"].paginator.object_list.values_list("pk", flat=True))
            self.assertNotEqual(ordering, fresh_order)
            self.assertEqual(token.call_count, 2)

    def test_random_tokens_are_validated_and_ignored_for_other_sorts(self):
        for path in ("/publications/?sort=random", f"/publications/{self.alpha_site.pk}/?order=random"):
            for seed in ("", "short", "g" * 32, "a" * 33):
                with self.subTest(path=path, seed=seed):
                    self.assertEqual(self.client.get(path + "&seed=" + seed).status_code, 400)
        for path in ("/publications/?sort=alpha", f"/publications/{self.alpha_site.pk}/?order=newest"):
            with self.subTest(path=path):
                response = self.client.get(path + "&seed=invalid")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("seed=", response.context["extra_query"])

    def test_filter_controls_use_joined_pairs_and_a_styled_sort_select(self):
        response = self.client.get("/publications/")
        self.assertContains(response, 'aria-label="Filter publications"')
        self.assertContains(response, 'aria-label="Apply or reset filters"')
        self.assertContains(response, 'class="site-directory__select"')
        self.assertContains(response, "Name (A–Z)")
        self.assertContains(response, "Name (Z–A)")

    def test_directory_is_paginated_and_keeps_filters_in_pagination_links(self):
        for index in range(settings.PUBLICATIONS_PAGE_SIZE):
            site = self.make_site(
                f"Site {index:02}",
                f"https://site-{index}.example.com",
                self.video_games,
                [self.news],
            )
            self.make_article(site, f"Article {index}")

        response = self.client.get(f"/publications/?category={self.video_games.pk}&sort=alpha")

        self.assertEqual(response.context["page_obj"].paginator.per_page, settings.PUBLICATIONS_PAGE_SIZE)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertIn(f"category={self.video_games.pk}", response.context["extra_query"])
        self.assertIn("sort=alpha", response.context["extra_query"])

    def test_publication_pages_are_in_the_sitemap(self):
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/publications/{self.alpha_site.pk}/")
        self.assertNotContains(response, f"/publications/{self.hidden_site.pk}/")


class PublicationArticlePageTests(PublicationsDirectoryTests):
    @override_settings(PUBLICATION_ARTICLES_PAGE_SIZE=2, PUBLICATION_ARTICLES_LIMIT=5)
    def test_random_article_pagination_preserves_the_capped_selection(self):
        for index in range(5):
            self.make_article(self.alpha_site, f"Random extra {index}")
        hidden = self.make_article(self.alpha_site, "Hidden random article", hidden=True)
        path = f"/publications/{self.alpha_site.pk}/"
        with patch("website.views.secrets.token_hex", return_value="c" * 32) as token:
            first = self.client.get(path + "?order=random")
            expected = list(first.context["page_obj"].paginator.object_list.values_list("pk", flat=True))
            first_ids = [article.pk for article in first.context["page_obj"]]
            self.assertEqual([card.item.pk for card in first.context["cards"]], first_ids)
            seen = first_ids[:]
            response = first
            while response.context["page_obj"].has_next():
                response = self.client_class().get(path + self.pagination_href(response, "next"))
                self.assertIn("seed=" + "c" * 32, response.context["extra_query"])
                page_ids = [article.pk for article in response.context["page_obj"]]
                self.assertEqual([card.item.pk for card in response.context["cards"]], page_ids)
                seen.extend(page_ids)
                if response.context["page_obj"].number == 2:
                    previous = self.client.get(path + self.pagination_href(response, "previous"))
                    self.assertEqual([article.pk for article in previous.context["page_obj"]], first_ids)
            self.assertEqual(seen, expected)
            self.assertEqual(len(seen), 5)
            self.assertEqual(len(set(seen)), 5)
            self.assertNotIn(hidden.pk, seen)
            self.assertEqual(token.call_count, 1)

    def test_site_articles_page_shows_details_and_newest_articles(self):
        response = self.client.get(f"/publications/{self.alpha_site.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "site_articles.html")
        self.assertContains(response, "Alpha Games")
        self.assertContains(response, "Alpha recent")
        self.assertLess(
            response.content.index(b"Alpha recent"),
            response.content.index(b"Alpha older"),
        )
        self.assertContains(response, "Newest")
        self.assertContains(response, "Popular")
        self.assertContains(response, "Random")

    def test_site_articles_can_be_sorted_by_popularity_or_randomly(self):
        Articles.objects.filter(site=self.alpha_site, title="Alpha older").update(clicks=100)

        popular = self.client.get(f"/publications/{self.alpha_site.pk}/?order=popular")
        random = self.client.get(f"/publications/{self.alpha_site.pk}/?order=random")

        self.assertLess(
            popular.content.index(b"Alpha older"),
            popular.content.index(b"Alpha recent"),
        )
        self.assertEqual(random.status_code, 200)
        self.assertContains(random, "Alpha older")
        self.assertContains(random, "Alpha recent")

    def test_site_articles_exclude_hidden_and_unknown_sites(self):
        hidden_site = Sites.objects.get(name="Hidden Site")

        self.assertEqual(self.client.get(f"/publications/{hidden_site.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/publications/999999/").status_code, 404)

    def test_site_articles_are_capped_at_250_and_paginated(self):
        for index in range(settings.PUBLICATION_ARTICLES_LIMIT):
            self.make_article(
                self.alpha_site,
                f"Extra article {index}",
                published=date.today() - timedelta(days=index + 2),
            )

        response = self.client.get(f"/publications/{self.alpha_site.pk}/?page=5")

        self.assertEqual(response.context["page_obj"].paginator.count, settings.PUBLICATION_ARTICLES_LIMIT)
        self.assertEqual(len(response.context["cards"]), settings.PUBLICATION_ARTICLES_PAGE_SIZE)

    def test_active_adverts_are_not_included_in_publication_feeds(self):
        today = date.today()
        Adverts.objects.create(
            title="Directory ad",
            message="Support this site",
            site_name="Sponsor",
            site_url="https://sponsor.example.com",
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
            concurrency=1,
            advert_size=self.advert_size,
        )

        response = self.client.get(f"/publications/{self.alpha_site.pk}/")

        self.assertNotContains(response, "Support this site")
        self.assertNotContains(response, "Sponsored")
