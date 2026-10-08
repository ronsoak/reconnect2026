# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
# Feed
#
# Builds the list of cards (articles and adverts) shown on the dynamic front page.
#
# Order of operations
#   1. Work out which adverts are live and how many advert cards they need.
#   2. Limit the pool of articles to the sites matching the category and tag filters.
#   3. Pick the newest articles, then random older articles, then popular articles.
#      Each step skips anything already picked.
#   4. Shuffle the articles together, give each a card size, then insert the adverts.
#
# Example (Django shell)
#   python manage.py shell -c "from website.feed import build_dynamic_feed; print(len(build_dynamic_feed()))"
#   python manage.py shell -c "from website.feed import build_dynamic_feed; print(len(build_dynamic_feed(category_ids=[1, 2], tag_ids=[5])))"
#
# Tests
#   python manage.py test website.test_feed
# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
import random
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

from .models import Adverts, Articles, Sites

# Total cards on the page, adverts included. Rounding up can push the total a little over.
FEED_SIZE = 100

# Share of the article slots given to each bucket. Popular takes whatever percentage is left.
NEW_PERCENT = 50
RANDOM_PERCENT = 30
POPULAR_PERCENT = 100 - NEW_PERCENT - RANDOM_PERCENT

# Random articles must be older than this many days.
RANDOM_MIN_AGE_DAYS = 7

# Popular articles are drawn at random from this many of the highest ranked articles.
POPULAR_POOL_SIZE = 100

# Share of the articles given the large and medium card sizes. The rest are small.
LARGE_PERCENT = 10
MEDIUM_PERCENT = 30

# Advert spacing: no advert within the first FIRST articles, and at least GAP articles between adverts.
ADVERT_FIRST_ALLOWED = 5
ADVERT_MIN_GAP = 5

# Advert sizes as stored in the Logic model.
ADVERT_SIZES = {
    "Feed Small": "small",
    "Feed Medium": "medium",
    "Feed Large": "large",
}


@dataclass
class FeedCard:
    kind: str  # "article" or "advert"
    item: Any  # the Articles or Adverts row
    size: str  # "small", "medium" or "large"

    @property
    def is_advert(self):
        return self.kind == "advert"


# ===== ===== ===== ===== ===== =====
# Helpers
# ===== ===== ===== ===== ===== =====
def ceil_percent(count, percent):
    """Rounds up using whole numbers only, so 50% of 100 is exactly 50 and 50% of 97 is 49."""
    return -(-count * percent // 100)


def has_valid_image(article):
    """An article can only be a medium or large card if it has an http(s) image address."""
    url = (article.image_url or "").strip().lower()
    return url.startswith(("http://", "https://"))


def advert_size(advert):
    """Maps the advert's size from the Logic model to small, medium or large."""
    return ADVERT_SIZES.get(advert.advert_size.value, "small")


def min_articles_for_adverts(advert_count):
    """The fewest articles needed to place this many adverts and still follow the spacing rules."""
    if advert_count <= 0:
        return 0
    return ADVERT_FIRST_ALLOWED + ADVERT_MIN_GAP * (advert_count - 1)


# ===== ===== ===== ===== ===== =====
# Article pool and buckets
# ===== ===== ===== ===== ===== =====
def visible_articles(category_ids=None, tag_ids=None):
    """
    Visible articles from the sites that match the filters.

    Several categories (or tags) are an 'or': a site matches if it has any of them.
    A category choice and a tag choice together are an 'and'.
    The sites are narrowed first so the article query only touches the sites that matter.
    """
    sites = Sites.objects.filter(hidden=False)
    if category_ids:
        sites = sites.filter(category_id__in=category_ids)
    if tag_ids:
        sites = sites.filter(tags__id__in=tag_ids)
    return Articles.objects.filter(
        hidden=False,
        site_hide=False,
        site__in=sites.values("pk"),
    )


def pick_newest(pool, count):
    """Newest first by published date. Articles sharing a date go by run_id, lowest first."""
    return list(
        pool.select_related("site").order_by("-published", "run_id", "pk")[:count]
    )


def pick_random(pool, count, exclude_ids, today, rng):
    """Random articles older than RANDOM_MIN_AGE_DAYS. Only ids are loaded, then the chosen rows are fetched."""
    cutoff = today - timedelta(days=RANDOM_MIN_AGE_DAYS)
    candidate_ids = list(
        pool.filter(published__lt=cutoff)
        .exclude(pk__in=exclude_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    chosen_ids = rng.sample(candidate_ids, min(count, len(candidate_ids)))
    return list(Articles.objects.filter(pk__in=chosen_ids).select_related("site"))


def pick_popular(pool, count, exclude_ids, rng):
    """
    Random articles from the top of the rank order.
    Articles already picked are skipped, so the next ranked article takes their place.
    """
    pool_size = max(POPULAR_POOL_SIZE, count)
    candidates = list(
        pool.exclude(pk__in=exclude_ids)
        .select_related("site")
        .order_by("-rank", "-published", "run_id", "pk")[:pool_size]
    )
    return rng.sample(candidates, min(count, len(candidates)))


# ===== ===== ===== ===== ===== =====
# Card sizes
# ===== ===== ===== ===== ===== =====
def build_article_cards(articles, rng):
    """
    Gives each article a card size at random: 10% large, 30% medium, the rest small.
    Only articles with a valid image can be large or medium, and large is filled first.
    """
    large_quota = ceil_percent(len(articles), LARGE_PERCENT)
    medium_quota = ceil_percent(len(articles), MEDIUM_PERCENT)

    with_image = [article for article in articles if has_valid_image(article)]
    rng.shuffle(with_image)
    large_ids = {article.pk for article in with_image[:large_quota]}
    medium_ids = {
        article.pk for article in with_image[large_quota:large_quota + medium_quota]
    }

    cards = []
    for article in articles:
        if article.pk in large_ids:
            size = "large"
        elif article.pk in medium_ids:
            size = "medium"
        else:
            size = "small"
        cards.append(FeedCard("article", article, size))
    return cards


# ===== ===== ===== ===== ===== =====
# Adverts
# ===== ===== ===== ===== ===== =====
def get_live_adverts(today):
    """Adverts running today that are allowed to appear at least once, earliest start date first."""
    return list(
        Adverts.objects.filter(start_date__lte=today, end_date__gte=today, concurrency__gt=0)
        .select_related("advert_size")
        .order_by("start_date", "pk")
    )


def expand_advert_slots(adverts):
    """One entry per appearance, so an advert with a concurrency of 2 is listed twice."""
    slots = []
    for advert in adverts:
        slots.extend([advert] * advert.concurrency)
    return slots


def insert_adverts(article_cards, advert_slots, at_end, rng):
    """
    Puts advert cards between the article cards.

    The spare articles (beyond the minimum needed for the spacing rules) are shared out
    evenly, so the adverts are spread across the page. When the rules cannot be followed
    the single advert goes at the end.
    """
    if not advert_slots:
        return list(article_cards)

    advert_slots = list(advert_slots)
    rng.shuffle(advert_slots)
    advert_cards = [FeedCard("advert", advert, advert_size(advert)) for advert in advert_slots]

    if at_end:
        return list(article_cards) + advert_cards

    advert_count = len(advert_cards)
    spare = len(article_cards) - min_articles_for_adverts(advert_count)

    # Number of articles that come before each advert
    positions = []
    for number in range(1, advert_count + 1):
        base = ADVERT_FIRST_ALLOWED + ADVERT_MIN_GAP * (number - 1)
        extra = (spare * number + (advert_count + 1) // 2) // (advert_count + 1)
        positions.append(base + extra)

    cards = []
    next_advert = 0
    for index, article_card in enumerate(article_cards):
        while next_advert < advert_count and positions[next_advert] == index:
            cards.append(advert_cards[next_advert])
            next_advert += 1
        cards.append(article_card)
    cards.extend(advert_cards[next_advert:])
    return cards


# ===== ===== ===== ===== ===== =====
# Dynamic feed
# ===== ===== ===== ===== ===== =====
def build_dynamic_feed(category_ids=None, tag_ids=None, feed_size=FEED_SIZE, today=None, rng=None):
    """
    Returns the list of FeedCard objects for the dynamic front page.

    category_ids / tag_ids: ids of Logic rows chosen in the filters (empty means no filter).
    feed_size: total cards wanted, adverts included.
    today / rng: only passed in by tests, to get repeatable results.
    """
    rng = rng or random.Random()
    today = today or timezone.localdate()

    # Adverts come first because they take slots away from the articles.
    live_adverts = get_live_adverts(today)
    advert_slots = expand_advert_slots(live_adverts)
    at_end = False
    if advert_slots and feed_size - len(advert_slots) < min_articles_for_adverts(len(advert_slots)):
        advert_slots = [live_adverts[0]]
        at_end = True

    article_total = max(feed_size - len(advert_slots), 0)
    new_count = ceil_percent(article_total, NEW_PERCENT)
    random_count = ceil_percent(article_total, RANDOM_PERCENT)
    popular_count = ceil_percent(article_total, POPULAR_PERCENT)

    # Each bucket skips what the earlier buckets picked.
    pool = visible_articles(category_ids, tag_ids)
    newest = pick_newest(pool, new_count)
    picked_ids = {article.pk for article in newest}
    older = pick_random(pool, random_count, picked_ids, today, rng)
    picked_ids.update(article.pk for article in older)
    popular = pick_popular(pool, popular_count, picked_ids, rng)

    # A tight filter can leave too few articles to follow the advert rules.
    articles = newest + older + popular
    if advert_slots and not at_end and len(articles) < min_articles_for_adverts(len(advert_slots)):
        advert_slots = [live_adverts[0]]
        at_end = True

    rng.shuffle(articles)
    article_cards = build_article_cards(articles, rng)
    return insert_adverts(article_cards, advert_slots, at_end, rng)
