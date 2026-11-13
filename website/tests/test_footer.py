from unittest import mock

from django.template import Context, Template
from django.test import RequestFactory, TestCase

from website.models import Articles, Logic, Sites


class FooterTests(TestCase):
    def test_home_header_and_footer_counts_use_thousands_separators(self):
        for count, formatted in ((999, "999"), (1000, "1,000"), (1234567, "1,234,567")):
            with self.subTest(count=count), mock.patch(
                "website.templatetags.footer_tags.visible_articles",
            ) as articles:
                articles.return_value.count.return_value = count
                response = self.client.get("/")
                self.assertContains(
                    response,
                    f'<span class="site-header__count-total">{formatted}</span>',
                    html=True,
                )
                self.assertContains(
                    response,
                    f'<span class="site-header__count-animated" aria-hidden="true">{formatted}</span>',
                    html=True,
                )
                self.assertContains(response, f'data-header-count="{count}"')
                self.assertContains(response, f"<strong>{formatted}</strong>", html=True)
                articles.return_value.count.assert_called_once_with()

    def test_count_is_reused_per_request_but_not_across_requests(self):
        with mock.patch("website.templatetags.footer_tags.visible_articles") as articles:
            articles.return_value.count.side_effect = [0, 1234]
            first = self.client.get("/privacy/")
            second = self.client.get("/privacy/")
        self.assertContains(first, "<strong>0</strong>", html=True)
        self.assertContains(second, "<strong>1,234</strong>", html=True)
        self.assertEqual(articles.return_value.count.call_count, 2)

    def test_included_components_share_one_real_count_query(self):
        template = Template(
            '{% include "components/footer.html" %}{% include "components/footer.html" %}'
        )
        request = RequestFactory().get("/")
        with self.assertNumQueries(1):
            output = template.render(Context({"request": request}))
        self.assertEqual(output.count("<strong>0</strong>"), 2)

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
            name="Publication", description="Writing",
            url="https://example.com", rss_feed="https://example.com/feed",
        )
        site.categories.add(category)
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
