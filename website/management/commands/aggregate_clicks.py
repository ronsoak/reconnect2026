# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Aggregate Clicks
#
# Totals the Clicks model into the Analytics model: one row per article or advert per month,
# dated the first of the month. Objects with no clicks in the month get no row.
# Safe to run again for the same month, the row is set to the current total, never added to.
# Run it before the Clicks model is purged. Rows already in Analytics are never deleted.
# --baseline instead snapshots all current article/advert totals into last month.
# Baselines require an empty target month and cannot be overwritten by this command.
#
# Command Examples
#   Last month (the normal monthly run):  python manage.py aggregate_clicks
#   A specific month:                     python manage.py aggregate_clicks --month 2026-09
#   The month so far:                     python manage.py aggregate_clicks --month current
#   Preview without saving:               python manage.py aggregate_clicks --dry-run
#   Preview post-import baseline:         python manage.py aggregate_clicks --baseline --dry-run
#   Save post-import baseline (once):      python manage.py aggregate_clicks --baseline
#
# Query examples (in python manage.py shell)
#   Analytics.objects.filter(type__value="Article", object_id=904).order_by("month")
#   Analytics.objects.filter(month="2026-09-01").order_by("-clicks")[:10]
#   Analytics.objects.filter(object_id=904).aggregate(Sum("clicks"))
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== =====
from datetime import date
from math import isfinite

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from website.models import Adverts, Analytics, Articles, Clicks, Logging, Logic


# ===== ===== ===== =====
# Helpers
# ===== ===== ===== =====
def first_of_month(day):
    return day.replace(day=1)


def next_month(first):
    return date(first.year + (first.month == 12), first.month % 12 + 1, 1)


def previous_month(first):
    return date(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1)


def parse_month(text, today):
    """'2026-09' -> 2026-09-01. Blank is last month and 'current' is this month."""
    if not text:
        return previous_month(first_of_month(today))
    if text == "current":
        return first_of_month(today)
    try:
        year, month = text.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        raise CommandError(f"Month must look like 2026-09, got {text!r}")


# ===== ===== ===== =====
# Command
# ===== ===== ===== =====
class Command(BaseCommand):
    help = "Total monthly Clicks, or snapshot imported totals into last month with --baseline."

    def add_arguments(self, parser):
        selection = parser.add_mutually_exclusive_group()
        selection.add_argument("--month", help="YYYY-MM, or 'current'. Default is last month.")
        selection.add_argument(
            "--baseline", action="store_true",
            help="Snapshot ALL current article and advert click totals into the previous calendar month.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Show the totals, save nothing.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["baseline"] and options["month"]:
            raise CommandError("--baseline cannot be combined with --month.")
        # Serialize aggregation/baseline writers on PostgreSQL, including an empty month.
        click_types = {
            entry.value: entry.pk
            for entry in Logic.objects.select_for_update().filter(
                logic_type="CLICK_TYPE",
            ).order_by("pk")
        }
        month = parse_month(options["month"], timezone.localdate())
        if Analytics.objects.filter(month=month, is_baseline=True).exists():
            raise CommandError(
                f"{month:%Y-%m} contains a baseline snapshot; it cannot be overwritten."
            )
        if options["baseline"]:
            self.save_baseline(month, click_types, options["dry_run"])
            return
        rows = (
            Clicks.objects.filter(date__gte=month, date__lt=next_month(month), type__isnull=False)
            .values("type", "article", "site")
            .annotate(total=Count("pk"))
        )

        # Clicks.article is text, so group again by whole-number id and skip anything else.
        totals = {}
        for row in rows:
            if not row["article"].isdigit():
                continue
            key = (row["type"], int(row["article"]))
            entry = totals.setdefault(key, {"site": row["site"], "clicks": 0})
            entry["clicks"] += row["total"]

        self.stdout.write(f"{month:%B %Y}: {len(totals)} articles and adverts with clicks")
        if options["dry_run"]:
            for (type_id, object_id), entry in sorted(totals.items(), key=lambda item: -item[1]["clicks"])[:20]:
                self.stdout.write(f"  type {type_id} id {object_id}: {entry['clicks']}")
            self.stdout.write(self.style.WARNING("Dry run, nothing saved"))
            return

        with transaction.atomic():
            for (type_id, object_id), entry in totals.items():
                Analytics.objects.update_or_create(
                    type_id=type_id, object_id=object_id, month=month,
                    defaults={"site_id": entry["site"], "clicks": entry["clicks"]},
                )
            Logging.objects.create(
                log_type="ANALYTICS_TASK", value=f"{month:%Y-%m}: {len(totals)} rows from {sum(e['clicks'] for e in totals.values())} clicks",
            )
        self.stdout.write(self.style.SUCCESS(f"Saved {len(totals)} analytics rows for {month:%Y-%m}"))

    def save_baseline(self, month, click_types, dry_run):
        if Analytics.objects.filter(month=month).exists():
            raise CommandError(
                f"{month:%Y-%m} already has Analytics rows; baseline requires an empty month."
            )
        if Analytics.objects.filter(is_baseline=True).exists():
            raise CommandError("A baseline snapshot already exists; it can only be captured once.")
        if not {"Article", "Advert"}.issubset(click_types):
            raise CommandError("Seed the Article and Advert CLICK_TYPE values before capturing a baseline.")

        snapshots = []
        total = 0
        for model, kind in ((Articles, "Article"), (Adverts, "Advert")):
            fields = ("pk", "clicks", "site_id") if model is Articles else ("pk", "clicks")
            for values in model.objects.order_by("pk").values_list(*fields).iterator():
                object_id, clicks = values[:2]
                if not isfinite(clicks) or clicks < 0 or not clicks.is_integer():
                    raise CommandError(
                        f"{kind} {object_id} has invalid baseline clicks {clicks!r}; "
                        "expected a finite, non-negative whole number. Nothing saved."
                    )
                snapshots.append(Analytics(
                    type_id=click_types[kind], object_id=object_id, month=month,
                    site_id=values[2] if model is Articles else None,
                    clicks=int(clicks), is_baseline=True,
                ))
                total += int(clicks)

        if not snapshots:
            raise CommandError("No articles or adverts found; import data before capturing a baseline.")
        self.stdout.write(
            f"Baseline for {month:%Y-%m}: {len(snapshots)} articles and adverts, {total} clicks "
            "(historical totals, not measured monthly activity)."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run, nothing saved"))
            return
        Analytics.objects.bulk_create(snapshots, batch_size=1000)
        Logging.objects.create(
            log_type="ANALYTICS_TASK",
            value=f"Baseline {month:%Y-%m}: {len(snapshots)} rows from {total} historical clicks",
        )
        self.stdout.write(self.style.SUCCESS(f"Saved baseline for {month:%Y-%m}"))
