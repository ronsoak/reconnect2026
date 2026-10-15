from django.test import TestCase

from website.models import Logic
from website.templatetags.search_tags import DEFAULT_PLACEHOLDER, search_placeholder


class SearchPlaceholderTests(TestCase):
    def test_default_when_none_saved(self):
        self.assertEqual(search_placeholder(), DEFAULT_PLACEHOLDER)

    def test_picks_a_saved_phrase(self):
        Logic.objects.create(logic_type="SEARCH_PLACEHOLDER", value="Find a dragon")
        self.assertEqual(search_placeholder(), "Find a dragon")

    def test_ignores_other_logic_types(self):
        Logic.objects.create(logic_type="TAG", value="News")
        self.assertEqual(search_placeholder(), DEFAULT_PLACEHOLDER)

    def test_search_bar_renders_phrase_and_submit_control(self):
        Logic.objects.create(logic_type="SEARCH_PLACEHOLDER", value="Find a dragon")
        response = self.client.get("/")
        self.assertContains(response, 'placeholder="Find a dragon"')
        self.assertContains(response, 'class="input site-search__input"')
        self.assertContains(response, '>Search</button>')

    def test_shared_header_orders_navigation_before_search(self):
        for path in ("/", "/newest/", "/popular/", "/publications/", "/about/", "/privacy/", "/search/?q=games"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                header = response.content.decode().split("</header>", 1)[0]
                self.assertLess(header.index('class="site-brand"'), header.index('class="site-menu"'))
                self.assertLess(header.index('class="site-menu"'), header.index('class="site-search"'))
                self.assertEqual(header.count('role="search"'), 1)

    def test_shared_header_uses_logo_image(self):
        header = self.client.get("/").content.decode().split("</header>", 1)[0]
        self.assertIn('images/branding/reconnect_full_title.svg', header)
        self.assertIn('alt="Reconnect"', header)
        self.assertIn('aria-label="Reconnect home"', header)
        self.assertNotIn("site-brand__name", header)
