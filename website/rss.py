from datetime import datetime, time

from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from .feed import visible_articles
from .models import Logic


RSS_FEED_ITEM_LIMIT = 50


class ArticlesFeed(Feed):
    title = "Reconnect"
    link = "/publications/"
    description = "Recent independent writing about video games and tabletop games."

    def get_object(self, request, category_id=None):
        if category_id is None:
            return None
        return get_object_or_404(
            Logic,
            pk=category_id,
            logic_type="CATEGORY",
        )

    def title(self, obj):
        if obj is None:
            return "Reconnect — All Articles"
        return f"Reconnect — {obj.value}"

    def description(self, obj):
        if obj is None:
            return "The latest articles from all publications on Reconnect."
        return f"The latest {obj.value} articles from publications on Reconnect."

    def items(self, obj=None):
        articles = visible_articles()
        if obj is not None:
            articles = articles.filter(site__category=obj)
        return (
            articles.filter(published__isnull=False)
            .select_related("site", "site__category")
            .order_by("-published", "run_id", "pk")[:RSS_FEED_ITEM_LIMIT]
        )

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return f"{item.site.name} · {item.site.category.value}"

    def item_link(self, item):
        return reverse("rss_article_click", kwargs={"pk": item.pk})

    def item_guid(self, item):
        return item.url

    def item_guid_is_permalink(self, item):
        return False

    def item_pubdate(self, item):
        published = datetime.combine(item.published, time.min)
        return timezone.make_aware(published, timezone.get_current_timezone())
