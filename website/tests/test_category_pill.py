from django.template.loader import render_to_string
from django.test import SimpleTestCase


class CategoryPillTests(SimpleTestCase):
    """The category label is a coloured dot plus the name; the slug class picks the dot colour."""

    def render(self, category):
        return render_to_string("components/category_pill.html", {"category": category}).strip()

    def test_known_categories_get_their_colour_class(self):
        expected = {
            "Video Games": "category-pill--video-games",
            "TTRPGs": "category-pill--ttrpgs",
            "Tabletop": "category-pill--tabletop",
            "TCG's": "category-pill--tcgs",
        }
        for name, css_class in expected.items():
            with self.subTest(name=name):
                html = self.render(name)
                self.assertIn(f'class="category-pill {css_class}"', html)
                self.assertIn('<span class="category-pill__dot" aria-hidden="true"></span>', html)
                self.assertIn(
                    f'<span class="category-pill__name">{name.replace(chr(39), "&#x27;")}</span>', html
                )

    def test_missing_category_renders_nothing(self):
        self.assertEqual(self.render(None), "")
        self.assertEqual(self.render(""), "")
