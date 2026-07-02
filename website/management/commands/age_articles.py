# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Last Article
#
# Gets articles older than 3 days with more than 3 clicks, and reduces their modifier score by .1,
#
# Command Examples
#   Default run (3 days lookback): python manage.py age_articles
#   Dry-run (no DB writes): python manage.py age_articles --dry-run
#   Backfill / age older articles (e.g., 365 days): python manage.py age_articles --days 365
#   Limit to a specific site (pk=5): python manage.py age_articles --site 5
#   Run a single large UPDATE instead of chunking: python manage.py age_articles --chunk-size 0
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from typing import Any, Iterable, List, Optional
from website.models import Articles, Sites, Logging

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = (
        "Reduce the modifier for old articles meeting thresholds and record an AGE_TASK log."
        " By default: published <= now-3d, clicks >= 3, modifier >= 0.3, decrement 0.1."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=3,
            help="How many days back to consider (default: 3).",
        )
        parser.add_argument(
            "--min-clicks",
            type=int,
            default=3,
            help="Minimum clicks required to consider decrementing (default: 3).",
        )
        parser.add_argument(
            "--min-modifier",
            type=float,
            default=0.3,
            help="Only decrement articles with modifier >= this value (default: 0.3).",
        )
        parser.add_argument(
            "--decrement",
            type=float,
            default=0.1,
            help="Amount to subtract from modifier (default: 0.1).",
        )
        parser.add_argument(
            "--site",
            type=int,
            help="Optional site PK to limit changes to a single site.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=1000,
            help="Number of rows to update per chunk (default: 1000). Use 0 for a single UPDATE.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many would be changed but do not perform updates.",
        )

    def _chunked(self, iterable: Iterable[int], size: int) -> Iterable[List[int]]:
        chunk: List[int] = []
        for item in iterable:
            chunk.append(item)
            if len(chunk) >= size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    def handle(self, *args: Any, **options: Any):
        days: int = options["days"]
        min_clicks: int = options["min_clicks"]
        min_modifier: float = options["min_modifier"]
        decrement: float = options["decrement"]
        site_pk: Optional[int] = options.get("site")
        chunk_size: int = int(options.get("chunk_size") or 1000)
        dry_run: bool = options.get("dry_run", False)

        cutoff_date = timezone.localdate() - timedelta(days=days)

        qs = Articles.objects.filter(
            published__lte=cutoff_date,
            hidden=False,
            site_hide=False,
            clicks__gte=min_clicks,
            modifier__gte=min_modifier,
        )

        if site_pk:
            qs = qs.filter(site_id=site_pk)

        total_candidates = qs.count()
        self.stdout.write(
            f"Candidates: {total_candidates} articles (published <= {cutoff_date}, clicks >= {min_clicks}, modifier >= {min_modifier})"
        )

        if total_candidates == 0:
            self.stdout.write("Nothing to do.")
            # Still write a log entry indicating zero aged if you prefer; current behavior writes a log below.
            updated_total = 0
            Logging.objects.create(
                log_type="AGE_TASK",
                value=f"Aging Articles: {updated_total} articles aged."
            )
            self.stdout.write("Logged AGE_TASK entry.")
            return

        if dry_run:
            self.stdout.write("Dry-run: no updates performed.")
            return

        # If chunk_size == 0, do a single DB UPDATE. Otherwise update in chunks of PKs.
        updated_total = 0
        try:
            if chunk_size <= 0:
                # Single bulk update: ensure modifier never goes below 0.0
                with transaction.atomic():
                    updated_total = qs.update(
                        modifier=Greatest(F("modifier") - Value(decrement), Value(0.0))
                    )
            else:
                # Collect pks and update in chunks to control transaction size
                pks = list(qs.values_list("pk", flat=True))
                for chunk in self._chunked(pks, chunk_size):
                    with transaction.atomic():
                        updated = Articles.objects.filter(pk__in=chunk).update(
                            modifier=Greatest(F("modifier") - Value(decrement), Value(0.0))
                        )
                        updated_total += updated
        except Exception as exc:
            self.stderr.write(f"Update failed: {exc}")
            return 1

        self.stdout.write(f"Updated modifier for {updated_total} articles (decrement={decrement}).")

        # Write AGE_TASK log (always write with the count)
        try:
            Logging.objects.create(
                log_type="AGE_TASK",
                value=f"Aging Articles: [{updated_total}] articles are now old."
            )
            self.stdout.write("Logged AGE_TASK entry.")
        except Exception as e:
            self.stderr.write(f"Failed to create Logging row: {e}")

        return 0