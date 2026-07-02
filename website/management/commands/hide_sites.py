# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Hide Sites
#
# This script looks for any sites that havn't posted an article in over 6 months and hides them.
# Any hidden site will trigger a hide articles script. 
#
# Command Examples 
#   Default run (hide sites older than 180 days): python manage.py hide_sites
#   Dry-run to preview which sites would be hidden: python manage.py hide_sites --dry-run
#   Backfill threshold (hide sites older than 365 days): python manage.py hide_sites --days 365
#   Limit number of sites hidden in one execution (hide at most 10): python manage.py hide_sites --limit 10
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from typing import Any, List, Optional
from website.models import Sites, Articles, Logging

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = (
        "Hide sites whose last_article is older than the given number of days "
        "(default 180). If any sites are hidden this command will call the "
        "`hide_articles` management command to sync Articles.site_hide, and will "
        "write a HIDE_SITES_TASK log recording how many sites were hidden."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=180,
            help="Threshold in days; sites with last_article greater than this will be hidden (default: 180).",
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
        days: int = options.get("days", 180)
        dry_run: bool = options.get("dry_run", False)
        limit: int = int(options.get("limit", 0))

        qs = Sites.objects.filter(hidden=False, last_article__gt=days).order_by("pk")
        if limit > 0:
            qs = qs[:limit]

        pks_to_hide: List[int] = list(qs.values_list("pk", flat=True))
        count_sites = len(pks_to_hide)

        if count_sites == 0:
            self.stdout.write(f"No sites found with last_article > {days}. Nothing to do.")
            # Still write a log entry if you want to record zero; change behaviour if you prefer no log on zero.
            Logging.objects.create(
                log_type="HIDE_SITES_TASK",
                value=f"Hiding Sites: {count_sites} Sites hidden.",
            )
            self.stdout.write("Logged HIDE_SITES_TASK entry (0).")
            return

        self.stdout.write(f"Found {count_sites} site(s) with last_article > {days}: PKs={pks_to_hide}")

        if dry_run:
            self.stdout.write("Dry-run enabled; the following site PKs would be hidden:")
            for pk in pks_to_hide:
                self.stdout.write(f" - {pk}")
            return

        # Update the Sites.hidden flag in a single query
        try:
            with transaction.atomic():
                updated = Sites.objects.filter(pk__in=pks_to_hide).update(hidden=True)
        except Exception as exc:
            self.stderr.write(f"Failed to update site hidden flags: {exc}")
            return 1

        self.stdout.write(f"Updated {updated} site(s) to hidden=True.")

        # Optionally compute how many articles will be affected (for information)
        try:
            articles_to_be_hidden = Articles.objects.filter(site_id__in=pks_to_hide).count()
        except Exception:
            articles_to_be_hidden = 0

        # Call the child command that syncs Articles.site_hide (synchronous call)
        try:
            self.stdout.write("Running hide_articles to sync Articles.site_hide...")
            call_command("hide_articles")
            self.stdout.write("hide_articles completed.")
        except Exception as exc:
            self.stderr.write(f"hide_articles command failed: {exc}")
            # We continue to write the HIDE_SITES_TASK log even if hide_articles fails.

        # Write Logging entry for the number of sites hidden
        try:
            Logging.objects.create(
                log_type="HIDE_SITES_TASK",
                value=f"Hiding Sites: {updated} Sites hidden.",
            )
            self.stdout.write(f"Logged HIDE_SITES_TASK: [{updated}] sites hidden.")
        except Exception as exc:
            self.stderr.write(f"Failed to write Logging row: {exc}")

        # Also print article info for convenience
        self.stdout.write(f"Articles affected (approx): {articles_to_be_hidden}")

        return 0