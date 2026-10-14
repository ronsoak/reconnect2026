# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Hide Sites
#
# Hide inactive sites and mark them dormant for the monthly recovery check.
# Any hidden site will trigger a hide articles script. 
#
# Command Examples 
#   Default run (hide sites older than 270 days, 9 months): python manage.py hide_sites
#   Dry-run to preview which sites would be hidden: python manage.py hide_sites --dry-run
#   Backfill threshold (hide sites older than 365 days): python manage.py hide_sites --days 365
#   Limit number of sites hidden in one execution (hide at most 10): python manage.py hide_sites --limit 10
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from typing import Any, List
from website.models import Sites, Articles, Logging

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = (
        "Hide and mark dormant sites whose last_article is older than the given number of days "
        "(default 270, about 9 months). If any sites are hidden this command will call the "
        "`hide_articles` management command to sync Articles.site_hide, and will "
        "write a HIDE_SITES_TASK log recording how many sites were hidden."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=270,
            help="Threshold in days; sites with last_article greater than this will be hidden (default: 270, about 9 months).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Don't perform any writes; just report what would change.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional limit on how many sites to hide this run (0 = no limit). Useful to throttle work.",
        )

    def handle(self, *args: Any, **options: Any):
        days: int = options.get("days", 270)
        dry_run: bool = options.get("dry_run", False)
        limit: int = int(options.get("limit", 0))
        if days < 0 or limit < 0:
            raise CommandError("--days and --limit must be non-negative.")

        qs = Sites.objects.filter(hidden=False, last_article__gt=days).order_by("pk")
        if limit > 0:
            qs = qs[:limit]

        pks_to_hide: List[int] = list(qs.values_list("pk", flat=True))
        count_sites = len(pks_to_hide)

        if count_sites == 0:
            self.stdout.write(f"No sites found with last_article > {days}. Nothing to do.")
            if not dry_run:
                Logging.objects.create(
                    log_type="HIDE_SITES_TASK",
                    value=f"Hiding Sites: {count_sites} Sites hidden.",
                )
                self.stdout.write("Logged HIDE_SITES_TASK entry (0).")
            return

        self.stdout.write(f"Found {count_sites} site(s) with last_article > {days}: PKs={pks_to_hide}")

        if dry_run:
            self.stdout.write("Dry-run enabled; the following site PKs would be hidden and marked dormant:")
            for pk in pks_to_hide:
                self.stdout.write(f" - {pk}")
            return

        # Keep the inactivity marker and article visibility in sync, or roll back both.
        with transaction.atomic():
            updated = Sites.objects.filter(
                pk__in=pks_to_hide, hidden=False, last_article__gt=days,
            ).update(hidden=True, dormant=True)
            articles_to_be_hidden = Articles.objects.filter(site_id__in=pks_to_hide).count()
            if updated:
                call_command("hide_articles", stdout=self.stdout, stderr=self.stderr)
            Logging.objects.create(
                log_type="HIDE_SITES_TASK",
                value=f"Hiding Sites: {updated} Sites hidden.",
            )

        self.stdout.write(f"Updated {updated} site(s) to hidden=True, dormant=True.")
        self.stdout.write(f"Articles affected (approx): {articles_to_be_hidden}")