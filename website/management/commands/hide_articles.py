# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Hide Articles
#
# This script hides or unhides articles based on the parent publication setting
#
# Command Examples
#   Sync all sites (hide/unhide as needed) and write a log: python manage.py hide_articles
#   Dry-run (show counts, no DB changes): python manage.py hide_articles --dry-run
#   Sync only a single site (pk=5): python manage.py hide_articles --site 5
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from typing import Any, Optional
from website.models import Articles, Sites, Logging

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = (
        "Sync Articles.site_hide from Sites.hidden.\n"
        "By default updates all sites; use --site <pk> to limit to one site.\n"
        "Use --dry-run to see counts without making changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--site",
            type=int,
            help="Optional site PK to sync only that site.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show counts of changes but do not write to the DB.",
        )

    def handle(self, *args: Any, **options: Any):
        site_pk: Optional[int] = options.get("site")
        dry_run: bool = options.get("dry_run", False)

        hidden_count = 0

        if site_pk is not None:
            try:
                site = Sites.objects.get(pk=site_pk)
            except Sites.DoesNotExist:
                self.stderr.write(f"Site with pk={site_pk} not found.")
                return 1

            desired_flag = site.hidden
            qs = Articles.objects.filter(site=site)
            to_change_qs = qs.exclude(site_hide=desired_flag)

            to_change_count = to_change_qs.count()
            total_count = qs.count()

            self.stdout.write(
                f"Site {site_pk} '{site.name}': total articles={total_count}, "
                f"articles to change={to_change_count} (set site_hide={desired_flag})"
            )

            if dry_run:
                self.stdout.write("Dry-run: no changes made.")
                # report what would have been hidden
                if desired_flag:
                    self.stdout.write(f"Would have hidden {to_change_count} articles.")
                return

            # Single atomic update for this site's articles
            try:
                with transaction.atomic():
                    updated = to_change_qs.update(site_hide=desired_flag)
                self.stdout.write(f"Updated {updated} articles for site {site_pk}.")
                # Count only those set to True (hidden) in this run
                hidden_count = updated if desired_flag else 0
            except Exception as e:
                self.stderr.write(f"Failed to update articles for site {site_pk}: {e}")
                return 1

        else:
            # No single-site specified: perform set-based updates across all sites.
            # Update articles for hidden=True sites (set site_hide=True)
            true_qs = Articles.objects.filter(site__hidden=True).exclude(site_hide=True)
            # Update articles for hidden=False sites (set site_hide=False)
            false_qs = Articles.objects.filter(site__hidden=False).exclude(site_hide=False)

            true_count = true_qs.count()
            false_count = false_qs.count()
            total_changes = true_count + false_count

            self.stdout.write(
                f"All sites: articles to set site_hide=True = {true_count}, "
                f"to set site_hide=False = {false_count} (total {total_changes})"
            )

            if dry_run:
                self.stdout.write("Dry-run: no changes made.")
                self.stdout.write(f"Would hide {true_count} articles.")
                return

            try:
                with transaction.atomic():
                    updated_true = true_qs.update(site_hide=True)
                    updated_false = false_qs.update(site_hide=False)
            except Exception as e:
                self.stderr.write(f"Failed to update articles: {e}")
                return 1

            self.stdout.write(
                f"Updated {updated_true} -> site_hide=True, {updated_false} -> site_hide=False."
            )
            hidden_count = updated_true

        # Write Logging entry for the number of articles hidden in this run.
        try:
            Logging.objects.create(
                log_type="HIDE_ARTICLES_TASK",
                value=f"Hiding Articles: {hidden_count} articles hidden.",
            )
            self.stdout.write(f"Logged HIDE_ARTICLES_TASK: [{hidden_count}] articles hidden.")
        except Exception as e:
            self.stderr.write(f"Failed to write Logging row: {e}")

        return 0