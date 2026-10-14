from django.template import Context, Template
from django.test import TestCase

from website.models import Articles, Logic, Sites


class FooterTests(TestCase):
    def test_footer_appears_on_public_pages_with_links_and_credits(self):
        for path in ("/", "/newest/", "/popular/", "/search/", "/publications/", "/about/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, 'aria-label="Footer navigation"')
                self.assertContains(response, "Developed by Alex Antra")
                self.assertContains(response, "Designed by Micah Tabak")
                self.assertContains(response, "<strong>0</strong>")
                self.assertContains(response, 'src="/static/js/footer.js"')

    def test_count_ignores_filters_and_excludes_hidden_content(self):
        category = Logic.objects.create(logic_type="CATEGORY", value="Games")
        site = Sites.objects.create(
            name="Publication", category=category, description="Writing",
            url="https://example.com", rss_feed="https://example.com/feed",
        )
        for index, (hidden, site_hide) in enumerate(((False, False), (True, False), (False, True))):
            Articles.objects.create(
                site=site, title="Article", url=f"https://example.com/{index}",
                image_url="", hidden=hidden, site_hide=site_hide,
            )
        self.client.cookies["reconnect_filters"] = "category=999999"
        response = self.client.get("/publications/?category=999999")
        self.assertContains(response, "<strong>1</strong>")
        self.assertContains(response, "article to discover")
        site.hidden = True
        site.save()
        self.assertContains(self.client.get("/about/"), "<strong>0</strong>")

    def test_about_count_can_be_reused_without_another_query(self):
        template = Template("{% load footer_tags %}{% footer_article_count %}")
        with self.assertNumQueries(0):
            self.assertEqual(template.render(Context({"article_count": 42})), "42")
