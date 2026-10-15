from datetime import date
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from website.feed import FeedCard


class ArticleCardTests(SimpleTestCase):
    def test_all_card_sizes_keep_source_and_link_without_publication_date(self):
        for size in ("small", "medium", "large"):
            for published in (date(2026, 10, 15), None):
                with self.subTest(size=size, published=published):
                    article = SimpleNamespace(
                        pk=1, title="Example article", published=published,
                        image_url="https://example.com/cover.jpg",
                        site=SimpleNamespace(
                            name="Example publication",
                            category=SimpleNamespace(value="Games"),
                        ),
                    )
                    html = render_to_string(
                        "components/article_card.html",
                        {"card": FeedCard("article", article, size)},
                    )
                    self.assertIn("Example publication", html)
                    self.assertIn('href="/go/1/"', html)
                    self.assertNotIn("<time", html)
                    self.assertNotIn("2026-10-15", html)
                    self.assertNotIn("15 Oct 2026", html)
