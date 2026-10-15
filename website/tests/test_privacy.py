from django.test import TestCase
from django.urls import reverse


class PrivacyTests(TestCase):
    def test_policy_sections_and_actual_tracking_disclosures(self):
        response = self.client.get(reverse("privacy"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "privacy.html")
        for text in (
            "Information collected", "Cookies and your choices",
            "Article and advert click tracking", "Third-party services",
            "Retention and security", "Privacy questions and requests",
            "reconnect_filters", "365 days", "reconnect_clicks", "24 hours",
            "up to 100", "calendar date", "do not store your IP address",
            "Google Fonts", "https://substack.com/privacy",
            "Automated aggregation and deletion schedules are not yet configured",
            "contact form is planned but not yet available",
        ):
            with self.subTest(text=text):
                self.assertContains(response, text)
        self.assertContains(response, 'href="/about/"')
        self.assertFalse(response.cookies)
        self.assertNotContains(response, "<iframe")

    def test_footer_link_only_and_sitemap(self):
        for path in ("/", "/about/", "/privacy/"):
            with self.subTest(path=path):
                html = self.client.get(path).content.decode()
                before_footer, footer = html.split('<footer class="footer site-footer">')
                self.assertNotIn('href="/privacy/"', before_footer)
                self.assertIn('href="/privacy/"', footer)
        self.assertContains(self.client.get("/sitemap.xml"), "/privacy/")
