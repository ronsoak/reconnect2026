from datetime import date, timedelta

from django.test import TestCase

from website.models import Adverts, Articles, Logic, Sites
from website.views import SITE_ARTICLE_LIMIT, SITE_ARTICLE_PAGE_SIZE, SITE_DIRECTORY_PAGE_SIZE


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
            category=category,
            site_type=cls.site_type,
            description=f"About {name}",
            hidden=hidden,
        )
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

    def test_directory_lists_only_visible_sites_with_visible_articles(self):
        response = self.client.get("/publications/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 publications")
        self.assertNotContains(response, "visible")
        self.assertEqual(
            [site.name for site in response.context["page_obj"]],
            ["Alpha Games", "Zulu Tabletop"],
        )
        self.assertEqual(
            response.context["page_obj"][0].visible_article_count,
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

    def test_sort_options_are_supported(self):
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
        self.assertEqual(invalid.context["sort"], "alpha")

    def test_directory_is_paginated_and_keeps_filters_in_pagination_links(self):
        for index in range(SITE_DIRECTORY_PAGE_SIZE):
            site = self.make_site(
                f"Site {index:02}",
                f"https://site-{index}.example.com",
                self.video_games,
                [self.news],
            )
            self.make_article(site, f"Article {index}")

        response = self.client.get(f"/publications/?category={self.video_games.pk}&sort=alpha")

        self.assertEqual(response.context["page_obj"].paginator.per_page, SITE_DIRECTORY_PAGE_SIZE)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertIn(f"category={self.video_games.pk}", response.context["extra_query"])
        self.assertIn("sort=alpha", response.context["extra_query"])

    def test_publication_pages_are_in_the_sitemap(self):
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"/publications/{self.alpha_site.pk}/")
        self.assertNotContains(response, f"/publications/{self.hidden_site.pk}/")


class PublicationArticlePageTests(PublicationsDirectoryTests):
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
        for index in range(SITE_ARTICLE_LIMIT):
            self.make_article(
                self.alpha_site,
                f"Extra article {index}",
                published=date.today() - timedelta(days=index + 2),
            )

        response = self.client.get(f"/publications/{self.alpha_site.pk}/?page=5")

        self.assertEqual(response.context["page_obj"].paginator.count, SITE_ARTICLE_LIMIT)
        self.assertEqual(len(response.context["cards"]), SITE_ARTICLE_PAGE_SIZE)

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
