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

    def test_search_bar_renders_phrase_and_is_square(self):
        Logic.objects.create(logic_type="SEARCH_PLACEHOLDER", value="Find a dragon")
        response = self.client.get("/")
        self.assertContains(response, 'placeholder="Find a dragon"')
        self.assertContains(response, "square-button")
