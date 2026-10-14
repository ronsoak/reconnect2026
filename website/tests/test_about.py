from django.test import TestCase

from website.models import Articles, Logic, Sites


class AboutPageTests(TestCase):
    def test_empty_counts_and_editable_sections(self):
        response = self.client.get("/about/")

        self.assertContains(response, "0 publications")
        self.assertContains(response, "0 articles")
        for template in (
            "components/about_intro.html",
            "components/about_newsletter.html",
            "components/about_using.html",
            "components/about_credits.html",
        ):
            with self.subTest(template=template):
                self.assertTemplateUsed(response, template)
        self.assertContains(response, "Newsletter signup embed to be added.")
        self.assertContains(response, 'href="/api/filters/"')
        self.assertContains(response, 'class="site-search"')
        self.assertNotContains(response, 'class="filter-bar"')
        self.assertNotContains(response, 'aria-label="Article feeds"')

    def test_counts_include_only_public_articles_and_their_publications(self):
        category = Logic.objects.create(logic_type="CATEGORY", value="Video Games")

        def make_site(name, hidden=False):
            return Sites.objects.create(
                name=name,
                url=f"https://{name}.example.com",
                rss_feed=f"https://{name}.example.com/feed",
                category=category,
                description="Test publication",
                hidden=hidden,
                article_count=999,
            )

        site = make_site("public")
        hidden_site = make_site("hidden", hidden=True)
        make_site("empty")
        for index, (parent, hidden, site_hide) in enumerate((
            (site, False, False),
            (site, False, False),
            (site, True, False),
            (site, False, True),
            (hidden_site, False, False),
        )):
            Articles.objects.create(
                title=f"Article {index}",
                url=f"https://articles.example.com/{index}",
                site=parent,
                hidden=hidden,
                site_hide=site_hide,
                image_url="",
            )

        self.client.cookies["reconnect_filters"] = "category=999999"
        response = self.client.get("/about/?category=999999")

        self.assertEqual(response.context["site_count"], 1)
        self.assertEqual(response.context["article_count"], 2)
        self.assertContains(response, "1 publication &middot; 2 articles")
        self.assertNotContains(response, "visible")
