# Builds the weekly newsletter export shown on the admin front page.
#
# Rules:
#   - A week runs Monday to Sunday and an article belongs to the week it was published in.
#   - Hidden articles, hidden sites and sites with recap switched off are left out.
#   - Titles containing a Newsletter Excluded Term (Logic model) as a whole word are left out,
#     so "review" removes "A review of X" but keeps "Preview".
#   - The top section is the articles with the most clicks that week (up to TOP_COUNT), and only
#     articles that had at least one click. Everything else follows in the remaining list.
#
# Use from the Django shell:
#   from website.newsletter import week_start_for, build_newsletter, render_markdown
#   data = build_newsletter(week_start_for("this"))
#   print(render_markdown(data))
import re
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from website.models import Articles, Clicks, Logic

TOP_COUNT = 30
EXCLUDED_TERM_TYPE = "NEWSLETTER_EXCLUDED_TERM"


def week_start_for(which, today=None):
    """Monday of the current week ('this') or of the previous week ('last')."""
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(days=7) if which == "last" else monday


def excluded_pattern():
    """One case-insensitive whole word pattern for all excluded terms, or None if there are none."""
    terms = Logic.objects.filter(logic_type=EXCLUDED_TERM_TYPE).values_list("value", flat=True)
    parts = [r"\b" + re.escape(term.strip()) + r"\b" for term in terms if term.strip()]
    return re.compile("|".join(parts), re.IGNORECASE) if parts else None


def build_newsletter(week_start):
    """Returns the week's dates, the top articles and the remaining articles."""
    week_end = week_start + timedelta(days=6)
    articles = (
        Articles.objects.filter(
            published__gte=week_start,
            published__lte=week_end,
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
        Clicks.objects.filter(type__value="Article", date__gte=week_start, date__lte=week_end)
        .values_list("article")
        .annotate(total=Count("id"))
    )
    for article in articles:
        article.week_clicks = counts.get(str(article.pk), 0)

    # Most clicks first, then lifetime rank, then newest
    articles.sort(key=lambda a: (-a.week_clicks, -(a.rank or 0), -a.published.toordinal(), a.pk))
    top = [a for a in articles if a.week_clicks > 0][:TOP_COUNT]
    top_ids = {a.pk for a in top}
    remaining = [a for a in articles if a.pk not in top_ids]
    remaining.sort(key=lambda a: (-(a.rank or 0), -a.published.toordinal(), a.pk))

    return {"week_start": week_start, "week_end": week_end, "top": top, "remaining": remaining}


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
    start, end = data["week_start"], data["week_end"]
    lines = [f"# Reconnect Recap: {start:%d %b} to {end:%d %b %Y}", ""]
    lines.append(f"## Top {TOP_COUNT} by clicks this week")
    lines.append("")
    if data["top"]:
        lines += [_line(a, i) for i, a in enumerate(data["top"], 1)]
    else:
        lines.append("No clicks recorded for this week's articles yet.")
    lines += ["", "## Everything else this week", ""]
    if data["remaining"]:
        lines += [_line(a) for a in data["remaining"]]
    else:
        lines.append("Nothing else.")
    return "\n".join(lines) + "\n"
