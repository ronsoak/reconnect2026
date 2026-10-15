from django.test import TestCase


class FloatingActionsTests(TestCase):
    """Back-to-top shows on every feed; refresh stays on the Dynamic feed only."""

    def test_back_to_top_on_all_feeds(self):
        for url in ("/", "/newest/", "/popular/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'data-scroll-top aria-label="Back to top"')
                self.assertContains(response, "js/floating_actions.js")

    def test_back_to_top_is_a_native_button(self):
        self.assertContains(self.client.get("/"), '<button type="button" class="button scroll-top-button"')

    def test_refresh_only_shares_the_group_on_dynamic(self):
        self.assertContains(self.client.get("/"), "refresh-button")
        for url in ("/newest/", "/popular/"):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "refresh-button")

    def test_not_on_other_pages(self):
        for url in ("/about/", "/privacy/", "/search/?q=test"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, "data-floating-actions")
                self.assertNotContains(response, "floating_actions.js")
