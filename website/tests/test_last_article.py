from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from website.models import Logic, Sites


class LastArticleTests(TestCase):
    def test_site_without_articles_is_stored_as_very_stale(self):
        category = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        site = Sites.objects.create(
            name="Empty", url="https://empty.example.com",
            rss_feed="https://empty.example.com/feed", category=category,
            description="Test site",
        )
        call_command("last_article", stdout=StringIO())
        site.refresh_from_db()
        self.assertEqual(site.last_article, 9999)

        # hide_sites picks it up with its default threshold
        call_command("hide_sites", stdout=StringIO())
        site.refresh_from_db()
        self.assertTrue(site.hidden)
