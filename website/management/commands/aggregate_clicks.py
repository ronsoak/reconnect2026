# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Aggregate Clicks
#
# Totals the Clicks model into the Analytics model: one row per article or advert per month,
# dated the first of the month. Objects with no clicks in the month get no row.
# Safe to run again for the same month, the row is set to the current total, never added to.
# Run it before the Clicks model is purged. Rows already in Analytics are never deleted.
#
# Command Examples
#   Last month (the normal monthly run):  python manage.py aggregate_clicks
#   A specific month:                     python manage.py aggregate_clicks --month 2026-09
#   The month so far:                     python manage.py aggregate_clicks --month current
#   Preview without saving:               python manage.py aggregate_clicks --dry-run
#
# Query examples (in python manage.py shell)
#   Analytics.objects.filter(type__value="Article", object_id=904).order_by("month")
#   Analytics.objects.filter(month="2026-09-01").order_by("-clicks")[:10]
#   Analytics.objects.filter(object_id=904).aggregate(Sum("clicks"))
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== =====
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from website.models import Analytics, Clicks, Logging


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
    help = "Total one month of Clicks into the Analytics model (default: last month)."

    def add_arguments(self, parser):
        parser.add_argument("--month", help="YYYY-MM, or 'current'. Default is last month.")
        parser.add_argument("--dry-run", action="store_true", help="Show the totals, save nothing.")

    def handle(self, *args, **options):
        month = parse_month(options["month"], timezone.localdate())
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
