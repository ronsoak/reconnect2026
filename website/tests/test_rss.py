from datetime import date, timedelta
from xml.etree import ElementTree

from django.test import TestCase

from website.models import Articles, Clicks, Logic, Sites
from django.conf import settings


class ArticlesFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.video_games = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.tabletop = Logic.objects.create(logic_type="CATEGORY", value="Tabletop")
        cls.rss_type = Logic.objects.create(logic_type="CLICK_TYPE", value="RSS")
        cls.site = Sites.objects.create(
            name="Game Journal",
            url="https://journal.example.com",
            rss_feed="https://journal.example.com/feed",
            category=cls.video_games,
            description="Game writing",
        )
        cls.tabletop_site = Sites.objects.create(
            name="Tabletop Journal",
            url="https://tabletop.example.com",
            rss_feed="https://tabletop.example.com/feed",
            category=cls.tabletop,
            description="Tabletop writing",
        )

    def add_article(self, site, title, **values):
        values.setdefault("published", date.today())
        return Articles.objects.create(
            title=title,
            url=f"{site.url}/{title.lower().replace(' ', '-')}",
            image_url="",
            site=site,
            **values,
        )

    def items(self, response):
        root = ElementTree.fromstring(response.content)
        return root.findall("./channel/item")

    def test_all_feed_has_recent_visible_articles_with_tracked_links(self):
        article = self.add_article(self.site, "A new article")

        response = self.client.get("/feeds/all.rss")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        items = self.items(response)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].findtext("title"), article.title)
        self.assertEqual(
            items[0].findtext("link"),
            f"http://testserver/go/rss/{article.pk}/",
        )
        self.assertEqual(items[0].findtext("guid"), article.url)
        self.assertEqual(items[0].find("guid").attrib["isPermaLink"], "false")

    def test_category_feed_only_contains_articles_from_that_category(self):
        video_article = self.add_article(self.site, "Video article")
        self.add_article(self.tabletop_site, "Tabletop article")

        response = self.client.get(f"/feeds/category/{self.video_games.pk}.rss")

        self.assertEqual(
            [item.findtext("title") for item in self.items(response)],
            [video_article.title],
        )

    def test_feeds_exclude_hidden_articles_and_hidden_sites(self):
        visible = self.add_article(self.site, "Visible article")
        self.add_article(self.site, "Hidden article", hidden=True)
        hidden_site = Sites.objects.create(
            name="Hidden Journal",
            url="https://hidden.example.com",
            rss_feed="https://hidden.example.com/feed",
            category=self.video_games,
            description="Hidden writing",
            hidden=True,
        )
        self.add_article(hidden_site, "Hidden site article")

        response = self.client.get("/feeds/all.rss")

        self.assertEqual(
            [item.findtext("title") for item in self.items(response)],
            [visible.title],
        )

    def test_feed_excludes_articles_without_publication_dates(self):
        self.add_article(self.site, "Dated article")
        self.add_article(self.site, "Undated article", published=None)

        titles = [item.findtext("title") for item in self.items(self.client.get("/feeds/all.rss"))]

        self.assertEqual(titles, ["Dated article"])

    def test_feed_is_limited_to_fifty_items(self):
        for index in range(settings.RSS_FEED_ITEM_LIMIT + 2):
            self.add_article(
                self.site,
                f"Article {index}",
                published=date.today() - timedelta(days=index),
            )

        items = self.items(self.client.get("/feeds/all.rss"))

        self.assertEqual(len(items), settings.RSS_FEED_ITEM_LIMIT)

    def test_rss_link_counts_and_records_click_then_deduplicates(self):
        article = self.add_article(self.site, "Clicked article")

        first = self.client.get(f"/go/rss/{article.pk}/")
        second = self.client.get(f"/go/rss/{article.pk}/")

        self.assertRedirects(first, article.url, fetch_redirect_response=False)
        self.assertRedirects(second, article.url, fetch_redirect_response=False)
        article.refresh_from_db()
        self.assertEqual(article.clicks, 1)
        click = Clicks.objects.get()
        self.assertEqual(click.type, self.rss_type)
        self.assertEqual(click.article, str(article.pk))
        self.assertEqual(click.site, self.site)

    def test_rss_redirect_rejects_hidden_articles_and_hidden_sites(self):
        hidden_article = self.add_article(self.site, "Hidden article", hidden=True)
        hidden_site = Sites.objects.create(
            name="Hidden Journal",
            url="https://hidden.example.com",
            rss_feed="https://hidden.example.com/feed",
            category=self.video_games,
            description="Hidden writing",
            hidden=True,
        )
        hidden_site_article = self.add_article(hidden_site, "Hidden site article")

        self.assertEqual(self.client.get(f"/go/rss/{hidden_article.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/go/rss/{hidden_site_article.pk}/").status_code, 404)
        self.assertEqual(Clicks.objects.count(), 0)

    def test_publications_page_links_to_all_and_category_feeds(self):
        response = self.client.get("/publications/")

        self.assertContains(response, "/feeds/all.rss")
        self.assertContains(response, f"/feeds/category/{self.video_games.pk}.rss")
        self.assertContains(response, f"/feeds/category/{self.tabletop.pk}.rss")
