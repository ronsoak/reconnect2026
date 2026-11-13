"""Read-only monthly analytics reports and their matching Markdown exports."""
from collections import defaultdict
from datetime import date
from html import escape
import re
from urllib.parse import quote

from django import forms
from django.db.models import Count, Q, Sum
from django.utils import timezone
from unfold.widgets import (
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
    UnfoldBooleanWidget,
)

from website.management.commands.aggregate_clicks import first_of_month, next_month, previous_month
from website.models import Adverts, Analytics, Articles, Clicks, Logging, Sites


class AnalyticsReportForm(forms.Form):
    report = forms.ChoiceField(
        choices=(("adverts", "Adverts"), ("sites", "Publications"), ("articles", "Articles")),
        widget=forms.HiddenInput,
    )
    period = forms.ChoiceField(
        choices=(
            ("month", "Calendar month"), ("year", "Calendar year"),
            ("rolling", "12 months ending in selected month"),
        ),
        widget=UnfoldAdminSelectWidget,
    )
    month = forms.DateField(
        required=False, input_formats=["%Y-%m"],
        widget=UnfoldAdminTextInputWidget(attrs={"type": "month"}),
        help_text="Used for monthly and rolling-12-month reports.",
    )
    year = forms.IntegerField(
        required=False, min_value=1900, max_value=9998, widget=UnfoldAdminIntegerFieldWidget,
        help_text="Used for calendar-year reports.",
    )
    object_id = forms.ChoiceField(
        required=False, label="Advert / publication", widget=UnfoldAdminSelectWidget,
    )
    include_baseline = forms.BooleanField(
        required=False, label="Show imported historical totals separately", widget=UnfoldBooleanWidget,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kind = self.data.get("report", "adverts")
        publication_filter = kind in {"sites", "articles"}
        model = Sites if publication_filter else Adverts
        name = "name" if publication_filter else "title"
        self.fields["object_id"].label = "Publication" if publication_filter else "Advert"
        self.fields["object_id"].choices = [
            ("", "All publications" if publication_filter else "All adverts"),
            *((str(pk), f"{label} (#{pk})") for pk, label in
              model.objects.order_by(name, "pk").values_list("pk", name)),
        ]

    def clean(self):
        cleaned = super().clean()
        today = timezone.localdate()
        month = cleaned.get("month") or previous_month(first_of_month(today))
        year = cleaned.get("year") or today.year
        if month.year < 1900 or month.year > 9998:
            self.add_error("month", "Choose a month between 1900 and 9998.")
            return cleaned
        period = cleaned.get("period")
        if period == "year":
            start, end = date(year, 1, 1), date(year, 12, 1)
        elif period == "rolling":
            end = month
            start = end
            for _ in range(11):
                start = previous_month(start)
        else:
            start = end = month
        cleaned.update(start=start, end=end)
        return cleaned


def build_report(kind, start, end, *, object_id=None, include_baseline=False, today=None):
    today = today or timezone.localdate()
    current = first_of_month(today)
    months = []
    month = start
    while month <= end:
        months.append(month)
        month = next_month(month)
    publication_filter = kind in {"sites", "articles"}
    types = ("Article", "RSS") if publication_filter else ("Advert",)
    saved = Analytics.objects.filter(
        month__gte=start, month__lte=end, type__logic_type="CLICK_TYPE", type__value__in=types,
    )
    if object_id:
        saved = saved.filter(site_id=object_id) if publication_filter else saved.filter(object_id=object_id)
    baseline_months = set(Analytics.objects.filter(
        month__gte=start, month__lte=end, is_baseline=True,
    ).order_by("month").values_list("month", flat=True).distinct())

    counts = defaultdict(int)
    article_counts = defaultdict(int)
    baseline = defaultdict(int)
    article_sites = {}
    saved_months = set()
    if include_baseline:
        entity_field = "site_id" if kind == "sites" else "object_id"
        baseline_fields = [entity_field, "month"]
        if kind == "articles":
            baseline_fields.append("site_id")
        for row in saved.filter(is_baseline=True).order_by().values(
            *baseline_fields,
        ).annotate(total=Sum("clicks")):
            baseline[(row[entity_field], row["month"])] += row["total"]
            if kind == "articles":
                article_sites[row["object_id"]] = row["site_id"]
    for row in saved.filter(is_baseline=False).values("month", "object_id", "site_id", "clicks"):
        entity_id = row["site_id"] if kind == "sites" else row["object_id"]
        if kind == "articles":
            article_sites[entity_id] = row["site_id"]
        saved_months.add(row["month"])
        # Current-month summaries may be stale; raw clicks are the sole source.
        if row["month"] >= current or row["month"] in baseline_months:
            continue
        counts[(entity_id, row["month"])] += row["clicks"]
        if kind == "sites":
            article_counts[(entity_id, row["object_id"])] += row["clicks"]

    completion_query = Q()
    for month in months:
        completion_query |= Q(value__startswith=f"{month:%Y-%m}: ")
    completed = set()
    for value in Logging.objects.filter(
        completion_query, log_type="ANALYTICS_TASK",
    ).values_list("value", flat=True):
        match = re.fullmatch(r"(\d{4}-\d{2}): \d+ rows from \d+ clicks", value)
        if match:
            completed.add(date.fromisoformat(match[1] + "-01"))

    if current in months and current not in baseline_months:
        raw = Clicks.objects.filter(
            date__gte=current, date__lte=today,
            type__logic_type="CLICK_TYPE", type__value__in=types,
        )
        if object_id:
            raw = raw.filter(site_id=object_id) if publication_filter else raw.filter(article=str(object_id))
        for row in raw.values("article", "site_id").annotate(total=Count("pk")):
            if not row["article"].isdigit():
                continue
            article_id = int(row["article"])
            entity_id = row["site_id"] if kind == "sites" else article_id
            if kind == "articles":
                article_sites[article_id] = row["site_id"]
            counts[(entity_id, current)] += row["total"]
            if kind == "sites":
                article_counts[(entity_id, article_id)] += row["total"]

    columns = []
    for month in months:
        if month in baseline_months:
            status, complete = "Imported baseline (excluded)", False
        elif month == current:
            status, complete = "Provisional: raw clicks to date", True
        elif month > current:
            status, complete = "Future month", False
        elif month in completed:
            status, complete = "Aggregated", True
        elif month in saved_months:
            status, complete = "Saved analytics: completion unverified", False
        else:
            status, complete = "Not aggregated", False
        columns.append({"month": month, "label": month.strftime("%b %Y"), "status": status, "complete": complete})

    observed_ids = {key[0] for key in counts} | {key[0] for key in baseline}
    if kind == "sites":
        entities = Sites.objects.order_by("name", "pk")
    elif kind == "articles":
        entities = Articles.objects.filter(pk__in=observed_ids)
    else:
        entities = Adverts.objects.filter(
            Q(start_date__lt=next_month(end), end_date__gte=start) | Q(pk__in=observed_ids),
        ).order_by("title", "pk")
    if object_id and kind != "articles":
        entities = (Sites if kind == "sites" else Adverts).objects.filter(pk=object_id)
    objects = {entity.pk: entity for entity in entities}
    entity_ids = set(objects) | observed_ids
    publication_names = {}
    if kind == "articles":
        for entity in objects.values():
            article_sites.setdefault(entity.pk, entity.site_id)
        site_ids = set(article_sites.values())
        if object_id:
            site_ids.add(int(object_id))
        publication_names = dict(Sites.objects.filter(pk__in=site_ids).values_list("pk", "name"))

    def identity(entity_id):
        entity = objects.get(entity_id)
        if entity is None:
            noun = {"sites": "publication", "articles": "article", "adverts": "advert"}[kind]
            return f"Deleted / unknown {noun} #{entity_id}" if entity_id else "Unknown publication", ""
        return (
            entity.name if kind == "sites" else entity.title,
            entity.site_url if kind == "adverts" else entity.url,
        )

    rows = []
    for entity_id in entity_ids:
        name, url = identity(entity_id)
        cells = []
        for column in columns:
            key = (entity_id, column["month"])
            excluded = column["month"] in baseline_months or column["month"] > current
            value = None if excluded else counts.get(key, 0 if column["complete"] else None)
            cells.append({"clicks": value})
        entity = objects.get(entity_id)
        rows.append({
            "id": entity_id, "name": name, "url": safe_url(url), "cells": cells,
            "publication": publication_names.get(article_sites.get(entity_id), "Unknown publication"),
            "total": sum(cell["clicks"] or 0 for cell in cells),
            "campaign": (
                f"{entity.start_date:%d %b %Y} to {entity.end_date:%d %b %Y}"
                if kind == "adverts" and entity else ""
            ),
        })
    rows.sort(key=lambda row: (-row["total"], row["name"].casefold(), row["id"] or 0))
    for i, column in enumerate(columns):
        values = [row["cells"][i]["clicks"] for row in rows]
        column["clicks"] = sum(value for value in values if value is not None) if any(
            value is not None for value in values
        ) or column["complete"] else None
    maximum = max((column["clicks"] or 0 for column in columns), default=0)
    for column in columns:
        column["bar_width"] = round((column["clicks"] or 0) * 1000 / maximum) if maximum else 0

    top = sorted(
        ((key, count) for key, count in article_counts.items() if count),
        key=lambda item: (-item[1], item[0][1]),
    )[:20]
    articles = Articles.objects.in_bulk(article_id for (_, article_id), _ in top)
    top_articles = []
    for (site_id, article_id), clicks in top:
        article = articles.get(article_id)
        top_articles.append({
            "title": article.title if article else f"Deleted article #{article_id}",
            "url": safe_url(article.url) if article else "",
            "site": identity(site_id)[0], "clicks": clicks,
        })
    baseline_rows = [
        {"name": identity(entity_id)[0], "month": month, "clicks": clicks}
        for (entity_id, month), clicks in sorted(
            baseline.items(), key=lambda item: (item[0][1], str(item[0][0])),
        )
    ]
    if object_id:
        selection = (
            publication_names[int(object_id)] if kind == "articles"
            else identity(int(object_id))[0]
        )
    else:
        selection = "All publications" if publication_filter else "All adverts"
    return {
        "kind": kind, "heading": {"sites": "Publication analytics", "articles": "Article analytics", "adverts": "Advert analytics"}[kind],
        "start": start, "end": end, "columns": columns, "rows": rows,
        "total": sum(row["total"] for row in rows), "top_articles": top_articles,
        "baseline_rows": baseline_rows, "include_baseline": include_baseline,
        "selection": selection,
        "incomplete": any(not column["complete"] for column in columns),
    }


def safe_url(value):
    return value if value.lower().startswith(("https://", "http://")) else ""


def markdown_text(value):
    text = escape(str(value)).replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_\[\]{}|#!])", r"\\\1", text)


def markdown_link(label, url):
    label = markdown_text(label)
    return f"[{label}]({quote(url, safe=':/?#=&%+~@!$*,-;')})" if url else label


def render_report_markdown(data):
    lines = [
        f"# Reconnect {data['heading']}", "",
        f"Period: {data['start']:%b %Y} to {data['end']:%b %Y}",
        f"Selection: {markdown_text(data['selection'])}", "",
        f"Recorded clicks (available months): **{data['total']}**", "",
        "These are recorded clicks, not unique visitors, impressions or click-through rates.",
        "Baseline snapshots are excluded from activity totals. Unavailable months are shown as N/A.",
        "Current-month figures are provisional. Saved months without a completion log may be incomplete.",
        "Article and RSS clicks are combined for publications and articles.", "",
        "## Monthly totals", "",
        "| Month | Recorded clicks | Status |", "| --- | ---: | --- |",
    ]
    for column in data["columns"]:
        clicks = column["clicks"] if column["clicks"] is not None else "N/A"
        lines.append(f"| {column['label']} | {clicks} | {column['status']} |")
    lines.extend(["", "## Results", ""])
    labels = " | ".join(column["label"] for column in data["columns"])
    detail_heading = (
        "Campaign dates | " if data["kind"] == "adverts"
        else "Publication | " if data["kind"] == "articles" else ""
    )
    lines.extend([
        f"| Name | {detail_heading}{labels} | Total |",
        "| --- | " + ("--- | " if detail_heading else "") + "---: | " * (len(data["columns"]) + 1),
    ])
    for row in data["rows"]:
        cells = " | ".join(str(cell["clicks"]) if cell["clicks"] is not None else "N/A" for cell in row["cells"])
        detail = (
            f"{row['campaign']} | " if data["kind"] == "adverts"
            else f"{markdown_text(row['publication'])} | " if data["kind"] == "articles" else ""
        )
        lines.append(f"| {markdown_link(row['name'], row['url'])} | {detail}{cells} | {row['total']} |")
    if not data["rows"]:
        lines.append("No matching recorded articles." if data["kind"] == "articles" else "No matching adverts or publications.")
    if data["top_articles"]:
        lines.extend(["", "## Top 20 articles by recorded clicks", ""])
        for row in data["top_articles"]:
            lines.append(
                f"- {markdown_link(row['title'], row['url'])} - "
                f"{markdown_text(row['site'])}: {row['clicks']} clicks"
            )
    if data["include_baseline"]:
        lines.extend(["", "## Imported historical totals (not monthly activity)", ""])
        for row in data["baseline_rows"]:
            lines.append(f"- {markdown_text(row['name'])}: {row['clicks']} clicks (snapshot month {row['month']:%Y-%m})")
        if not data["baseline_rows"]:
            lines.append("No baseline snapshots in the selected period.")
    return "\n".join(lines) + "\n"
