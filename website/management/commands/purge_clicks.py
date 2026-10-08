# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Purge Clicks
#
# Deletes one whole month of rows from the Clicks model, the month that is four months back.
# Run in October 2026 it deletes June 2026 and keeps July, August, September and October,
# so there is always at least 90 days of raw clicks to fall back on.
#
# Safety checks, the month is only deleted when:
#   - it is at least four months old (this can't be changed)
#   - the Analytics model already holds the month, and its click total matches the number
#     of Clicks rows. If not, run aggregate_clicks first. Nothing is deleted.
# Only Clicks rows are deleted. Analytics is never touched.
#
# Command Examples
#   Preview what would go:                python manage.py purge_clicks --dry-run
#   The normal monthly run:               python manage.py purge_clicks
#   Catch up on an older month:           python manage.py purge_clicks --month 2026-05
#   Delete even though totals differ:     python manage.py purge_clicks --force
#     (only use --force after looking at the dry run, e.g. for rows with no click type)
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== =====
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from website.management.commands.aggregate_clicks import first_of_month, next_month, parse_month, previous_month
from website.models import Analytics, Clicks, Logging

# How many months of clicks are kept in full
KEEP_MONTHS = 4


# ===== ===== ===== =====
# Helpers
# ===== ===== ===== =====
def newest_purgeable_month(today):
    """First of the month KEEP_MONTHS back, 2026-10-08 -> 2026-06-01."""
    month = first_of_month(today)
    for _ in range(KEEP_MONTHS):
        month = previous_month(month)
    return month


# ===== ===== ===== =====
# Command
# ===== ===== ===== =====
class Command(BaseCommand):
    help = "Delete the month of Clicks that is four months old, once it is safely in Analytics."

    def add_arguments(self, parser):
        parser.add_argument("--month", help="YYYY-MM. Must be four or more months ago. Default is exactly four months ago.")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted, delete nothing.")
        parser.add_argument("--force", action="store_true", help="Delete even if Analytics doesn't match the Clicks rows.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        limit = newest_purgeable_month(today)
        month = parse_month(options["month"], today) if options["month"] else limit
        if month > limit:
            raise CommandError(f"{month:%Y-%m} is too recent. The newest month that can be purged is {limit:%Y-%m}.")

        rows = Clicks.objects.filter(date__gte=month, date__lt=next_month(month))
        count = rows.count()
        saved = Analytics.objects.filter(month=month).aggregate(total=Sum("clicks"))["total"] or 0
        self.stdout.write(f"{month:%B %Y}: {count} click rows, {saved} clicks saved in Analytics")

        if count == 0:
            self.stdout.write("Nothing to purge")
            return

        if count != saved and not options["force"]:
            raise CommandError(
                f"Analytics ({saved}) doesn't match Clicks ({count}) for {month:%Y-%m}. "
                f"Run: python manage.py aggregate_clicks --month {month:%Y-%m}  Nothing was deleted."
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Dry run, {count} rows would be deleted"))
            return

        with transaction.atomic():
            deleted, _ = rows.delete()
            Logging.objects.create(log_type="ANALYTICS_TASK", value=f"Purged {deleted} clicks from {month:%Y-%m}")
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} click rows for {month:%Y-%m}"))
