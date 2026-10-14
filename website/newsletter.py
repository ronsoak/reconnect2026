# Builds the weekly and monthly newsletter exports shown on the admin front page.
#
# Rules:
#   - A week runs Monday to Sunday; a month is a calendar month. An article belongs to the
#     period it was published in.
#   - Hidden articles, hidden sites and sites with recap switched off are left out.
#   - Titles containing a Newsletter Excluded Term (Logic model) as a whole word are left out,
#     so "review" removes "A review of X" but keeps "Preview".
#   - The top section is the articles with the most clicks in the period (30 for a week, 60 for a
#     month), and only articles that had at least one click. Everything else follows in the remaining list.
#
# Use from the Django shell:
#   from website.newsletter import period_range, build_newsletter, render_markdown
#   start, end, top_count = period_range("month", "last")
#   data = build_newsletter(start, end, top_count)
#   print(render_markdown(data))
import re
import calendar
from datetime import date, timedelta

from django.db.models import Count
from django.utils import timezone

from website.models import Articles, Clicks, Logic

TOP_COUNT = 30
MONTH_TOP_COUNT = 60
EXCLUDED_TERM_TYPE = "NEWSLETTER_EXCLUDED_TERM"


def week_start_for(which, today=None):
    """Monday of the current week ('this') or of the previous week ('last')."""
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(days=7) if which == "last" else monday


def month_range_for(which, today=None):
    """First and last day of the current ('this') or previous ('last') calendar month."""
    today = today or timezone.localdate()
    year, month = today.year, today.month
    if which == "last":
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def period_range(period, which, today=None):
    """Returns (start, end, top_count) for a 'week' or 'month' and 'this' or 'last'."""
    if period == "month":
        start, end = month_range_for(which, today)
        return start, end, MONTH_TOP_COUNT
    start = week_start_for(which, today)
    return start, start + timedelta(days=6), TOP_COUNT


def excluded_pattern():
    """One case-insensitive whole word pattern for all excluded terms, or None if there are none."""
    terms = Logic.objects.filter(logic_type=EXCLUDED_TERM_TYPE).values_list("value", flat=True)
    parts = [r"\b" + re.escape(term.strip()) + r"\b" for term in terms if term.strip()]
    return re.compile("|".join(parts), re.IGNORECASE) if parts else None


def build_newsletter(start, end=None, top_count=TOP_COUNT):
    """Returns the period's dates, the top articles and the remaining articles.

    end defaults to six days after start, which is a Monday to Sunday week.
    """
    end = end or start + timedelta(days=6)
    articles = (
        Articles.objects.filter(
            published__gte=start,
            published__lte=end,
            hidden=False,
            site_hide=False,
            site__hidden=False,
            site__recap=True,
        )
        .select_related("site__category")
        .prefetch_related("site__tags")
    )

    pattern = excluded_pattern()
    if pattern:
        articles = [a for a in articles if not pattern.search(a.title)]
    else:
        articles = list(articles)

    # Clicks recorded this week for each article (Clicks.article holds the article id as text)
    counts = dict(
        Clicks.objects.filter(type__value="Article", date__gte=start, date__lte=end)
        .values_list("article")
        .annotate(total=Count("id"))
    )
    for article in articles:
        article.week_clicks = counts.get(str(article.pk), 0)

    # Most clicks first, then lifetime rank, then newest
    articles.sort(key=lambda a: (-a.week_clicks, -(a.rank or 0), -a.published.toordinal(), a.pk))
    top = [a for a in articles if a.week_clicks > 0][:top_count]
    top_ids = {a.pk for a in top}
    remaining = [a for a in articles if a.pk not in top_ids]
    remaining.sort(key=lambda a: (-(a.rank or 0), -a.published.toordinal(), a.pk))

    return {"start": start, "end": end, "top_count": top_count, "top": top, "remaining": remaining}


def _line(article, number=None):
    title = article.title.replace("[", "(").replace("]", ")")
    tags = ", ".join(sorted(t.value for t in article.site.tags.all()))
    prefix = f"{number}. " if number else "- "
    return (
        f"{prefix}[{title}]({article.url})\n"
        f"   {article.site.name} | {article.site.category.value} | {tags or 'No tags'} "
        f"| {article.week_clicks} clicks"
    )


def render_markdown(data):
    start, end, top_count = data["start"], data["end"], data["top_count"]
    # A full calendar month reads better as "Month Year" than as a date range
    monthly = top_count == MONTH_TOP_COUNT
    period = "month" if monthly else "week"
    title = f"{start:%B %Y}" if monthly else f"{start:%d %b} to {end:%d %b %Y}"
    lines = [f"# Reconnect Recap: {title}", ""]
    lines.append(f"## Top {top_count} by clicks this {period}")
    lines.append("")
    if data["top"]:
        lines += [_line(a, i) for i, a in enumerate(data["top"], 1)]
    else:
        lines.append(f"No clicks recorded for this {period}'s articles yet.")
    lines += ["", f"## Everything else this {period}", ""]
    if data["remaining"]:
        lines += [_line(a) for a in data["remaining"]]
    else:
        lines.append("Nothing else.")
    return "\n".join(lines) + "\n"
