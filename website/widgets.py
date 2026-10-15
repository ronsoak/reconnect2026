"""Dynamic-page widget data and source-order spacing."""

import random
from datetime import timedelta

from django.db.models import CharField, Count
from django.db.models.functions import Cast
from django.utils import timezone

from website.feed import FeedCard, visible_articles
from website.models import Clicks, Sites


WIDGET_MIN_CARDS = 10


def highlight_pool(category_ids=None, tag_ids=None, today=None):
    """Current-month click events, including RSS, not lifetime rank or publication date."""
    today = today or timezone.localdate()
    articles = visible_articles(category_ids, tag_ids).select_related("site", "site__category")
    public_ids = articles.order_by().annotate(
        click_id=Cast("pk", output_field=CharField()),
    ).values("click_id")
    counts = list(
        Clicks.objects.filter(
            type__logic_type="CLICK_TYPE", type__value__in=("Article", "RSS"),
            date__gte=today.replace(day=1), date__lte=today,
            article__in=public_ids,
        )
        .order_by().values("article").annotate(total=Count("pk"))
        .order_by("-total", "article")[:50]
    )
    by_id = articles.in_bulk([int(row["article"]) for row in counts])
    pool = []
    for row in counts:
        article = by_id.get(int(row["article"]))
        if article is not None:
            article.month_clicks = row["total"]
            pool.append(article)
    return pool


def widget_slots(card_count, kinds, rng=None):
    """Evenly distributed, jittered targets with ten ordinary cards between widgets."""
    rng = rng or random
    kinds = list(kinds[:card_count // WIDGET_MIN_CARDS])
    if not kinds:
        return []
    positions = []
    previous = 0
    for index in range(len(kinds)):
        target = card_count * (index + 1) // (len(kinds) + 1)
        low = max(previous + WIDGET_MIN_CARDS, target - 5)
        high = min(card_count - WIDGET_MIN_CARDS * (len(kinds) - index - 1), target + 5)
        position = rng.randint(low, max(low, high))
        positions.append(position)
        previous = position
    # Newest Additions retains its existing position-11-through-50 rule.
    rng.shuffle(kinds)
    if "newest" in kinds:
        eligible = [
            index for index, position in enumerate(positions) if position + index <= 49
        ]
        if not eligible:
            positions[0] = 49
            eligible = [0]
        index = rng.choice(eligible)
        kinds.remove("newest")
        kinds.insert(index, "newest")
    return [{"kind": kind, "after": position} for kind, position in zip(kinds, positions)]


def dynamic_widgets(cards, category_ids=None, tag_ids=None):
    today = timezone.localdate()
    articles = visible_articles(category_ids, tag_ids)
    recent_ids = list(articles.filter(
        published__gte=today - timedelta(days=7), published__lte=today,
    ).order_by().values_list("pk", flat=True))
    ticker_ids = random.sample(recent_ids, min(10, len(recent_ids)))
    ticker = articles.in_bulk(ticker_ids)
    newest = list(Sites.objects.filter(
        pk__in=articles.order_by().values("site_id"),
    ).order_by("-pk")[:10])
    pool = list(highlight_pool(category_ids, tag_ids, today))
    highlights = random.sample(pool, min(3, len(pool)))
    context = {
        "newest_additions": newest,
        "ticker_articles": [ticker[pk] for pk in ticker_ids],
        "highlight_cards": [FeedCard("article", article, "large") for article in highlights],
    }
    kinds = [
        kind for kind, available in (
            ("newest", newest), ("ticker", ticker_ids), ("highlight", highlights),
        ) if available
    ]
    context["widget_slots"] = widget_slots(len(cards), kinds)
    return context
