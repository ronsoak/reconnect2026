# ===== ===== ===== ===== ===== ===== ===== =====
# Sitemap
#
# Lists the public pages for search engines at /sitemap.xml
# Add a page's url name to `items` as each new page is built.
# ===== ===== ===== ===== ===== ===== ===== =====
from django.contrib.sitemaps import Sitemap
from django.db.models import Count, Q
from django.urls import reverse

from .models import Sites


class StaticPagesSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["home", "about", "publications"]

    def location(self, item):
        return reverse(item)


class SiteArticlesSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return (
            Sites.objects.filter(hidden=False)
            .annotate(
                visible_article_count=Count(
                    "articles",
                    filter=Q(articles__hidden=False, articles__site_hide=False),
                    distinct=True,
                )
            )
            .filter(visible_article_count__gt=0)
            .order_by("pk")
        )

    def location(self, item):
        return reverse("site_articles", kwargs={"site_id": item.pk})
