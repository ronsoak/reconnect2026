# ===== ===== ===== ===== ===== ===== ===== =====
# Sitemap
#
# Lists the public pages for search engines at /sitemap.xml
# Add a page's url name to `items` as each new page is built.
# ===== ===== ===== ===== ===== ===== ===== =====
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticPagesSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return ["home", "about"]

    def location(self, item):
        return reverse(item)
