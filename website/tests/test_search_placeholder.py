from django.test import TestCase
from django.urls import reverse

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

    def test_main_menu_links_and_current_page(self):
        expected = {
            "/": ('href="/" class="site-menu__link" aria-current="page"',),
            "/newest/": ('href="/" class="site-menu__link" aria-current="true"',),
            "/publications/": ('href="/publications/" class="site-menu__link" aria-current="page"',),
            "/about/": ('href="/about/" class="site-menu__link" aria-current="page"',),
        }
        for path, snippets in expected.items():
            with self.subTest(path=path):
                header = self.client.get(path).content.decode().split("</header>", 1)[0]
                for label in (">Home</a>", ">Publications</a>", ">About</a>"):
                    self.assertIn(label, header)
                for snippet in snippets:
                    self.assertIn(snippet, header)
                nav = header.split('class="site-menu"', 1)[1].split("</nav>", 1)[0]
                self.assertEqual(nav.count("aria-current="), 1)
                # The hamburger toggle starts hidden so the links still work without JavaScript.
                self.assertIn('aria-controls="site-menu-list" hidden', header)

    def test_privacy_page_marks_no_menu_item_current(self):
        header = self.client.get("/privacy/").content.decode().split("</header>", 1)[0]
        nav = header.split('class="site-menu"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("aria-current=", nav)


class HeaderTaglineTests(TestCase):
    """The second header row shows the subtitle and the public article count."""

    def test_header_shows_tagline_and_article_count(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, '<p class="site-header__tagline">For all things games writing</p>', html=True)
        self.assertContains(response, 'class="site-header__count"')
        self.assertRegex(response.content.decode(), r'site-header__count">\d+ Articles?<')
