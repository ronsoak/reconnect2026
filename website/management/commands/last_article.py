# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Last Article
#
# Counts how many days there have been since the last article was loaded.
# 
# Command Examples
#   Run for all visible sites (default chunk size 200): python manage.py last_article
#   Run for a single site (pk=5): python manage.py last_article --site 5
#   Dry-run to see how many would change without writing: python manage.py last_article --dry-run
#   Use a larger chunk size (or set 0/1 depending on DB and memory — chunk_size must be >=1): python manage.py last_article --chunk-size 500
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from typing import Any, Iterable, List, Optional
from website.models import Sites, Articles, Logging

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = (
        "Update Sites.last_article to be the number of days since the newest Article.published."
        " Writes a Logging entry with log_type='LAST_ARTICLE_TASK' when finished."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--site",
            type=int,
            help="If provided, only update this site by PK (useful for testing).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute changes and print a summary but do not write to the database.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=200,
            help="How many Sites to bulk_update at once (default: 200).",
        )

    def _chunked(self, iterable: Iterable, size: int) -> Iterable[List]:
        chunk: List = []
        for item in iterable:
            chunk.append(item)
            if len(chunk) >= size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    def handle(self, *args: Any, **options: Any):
        site_pk: Optional[int] = options.get("site")
        dry_run: bool = options.get("dry_run", False)
        chunk_size: int = max(1, int(options.get("chunk_size") or 200))

        today: date = timezone.localdate()

        qs = Sites.objects.filter(hidden=False)
        if site_pk:
            qs = qs.filter(pk=site_pk)

        # Annotate latest published date in a single query to avoid N+1 lookups.
        # Uses reverse relation name 'articles' as in your project code.
        qs = qs.annotate(latest_published=Max("articles__published")).order_by("pk")

        sites_to_update: List[Sites] = []
        total = 0
        updated = 0
        no_articles = 0

        for site in qs:
            total += 1
            latest = getattr(site, "latest_published", None)
            if latest is None:
                new_days = -1
                no_articles += 1
            else:
                delta_days = (today - latest).days
                new_days = max(delta_days, 0)

            if site.last_article != new_days:
                site.last_article = new_days
                sites_to_update.append(site)
                updated += 1

        self.stdout.write(f"Found {total} site(s) to consider (hidden=False).")
        self.stdout.write(f"Sites with no articles: {no_articles}")
        self.stdout.write(f"Sites that will be updated: {updated}")

        if dry_run:
            self.stdout.write("Dry-run enabled; no database writes will be performed.")
            return

        # Bulk update in chunks to avoid large transactions / memory usage
        for chunk in self._chunked(sites_to_update, chunk_size):
            Sites.objects.bulk_update(chunk, ["last_article"], batch_size=len(chunk))

        self.stdout.write(f"Updated {updated} site(s) last_article successfully.")

        # Write Logging entry for the run
        try:
            Logging.objects.create(
                log_type="LAST_ARTICLE_TASK",
                value=f"Last Article: Updated [{updated}] sites.",
            )
            self.stdout.write("Logged LAST_ARTICLE_TASK entry.")
        except Exception as e:
            self.stderr.write(f"Failed to write Logging row: {e}")