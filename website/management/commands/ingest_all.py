# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Ingest All
#
# Used for Ingesting all batches.
#
# Command Examples
#   Run all batches with default lookback (14 days): python manage.py ingest_all
#   Run all batches but backfill 365 days: python manage.py ingest_all --days 365
#   Run only batch 3 with the default 14-day lookback: python manage.py ingest_all --batch 3
#   Run only batch 3 and backfill 365 days: python manage.py ingest_all --batch 3 --days 365
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db import transaction
from django.db.models import Max
from typing import Any, Optional
from website.models import Sites, Logging, Articles
import time

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== =====
class Command(BaseCommand):
    help = "Runs through all the batches for ingestion, or a single batch when --batch is provided."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="How many days back to import (default: 14). Pass a larger value to backfill.",
        )
        parser.add_argument(
            "--batch",
            type=int,
            help="Optional: run only this batch number (0-based). If omitted the command runs all batches.",
        )

    def handle(self, *args: Any, **options: Any):
        days: int = options.get("days", 14)
        single_batch: Optional[int] = options.get("batch")

        # Reserve a new run id atomically so concurrent callers cannot obtain the same run.
        retry_attempts = 5
        backoff = 0.1
        new_run = None
        current_run = None

        try:
            for attempt in range(retry_attempts):
                try:
                    with transaction.atomic():
                        # Try to lock an existing row first
                        qs = Logging.objects.select_for_update().filter(log_type="INGEST_RUN_ID")
                        log_entry = qs.first()
                        if log_entry is None:
                            # No existing row: create-or-get (may raise IntegrityError on race)
                            log_entry, created = Logging.objects.get_or_create(
                                log_type="INGEST_RUN_ID",
                                defaults={"value": "0"},
                            )
                            # If created==True, row was created now; otherwise we have the existing row.
                        # At this point we have a log_entry instance (locked if it existed)
                        try:
                            current_run = int(log_entry.value) if log_entry.value is not None else 0
                        except (TypeError, ValueError):
                            current_run = 0
                        new_run = current_run + 1
                        # Persist the reserved run id
                        log_entry.value = str(new_run)
                        log_entry.save(update_fields=["value"])
                    # success -> break out
                    break
                except IntegrityError:
                    # Race while creating the initial row; retry with exponential backoff
                    if attempt + 1 >= retry_attempts:
                        raise
                    time.sleep(backoff)
                    backoff *= 2
            else:
                # exhausted retries (shouldn't happen because we raise above)
                raise CommandError("Failed to reserve INGEST_RUN_ID after retries")
        except Exception as exc:
            raise CommandError(f"Failed to reserve INGEST_RUN_ID: {exc}") from exc

        # safe prints (strings)
        self.stdout.write(f"Reserved run id {new_run} (previous {current_run}). days={days}")

        # Determine batches to run
        if single_batch is not None:
            batches = [single_batch]
        else:
            agg = Sites.objects.aggregate(max_batch=Max("batch_num"))
            max_batch = agg.get("max_batch")
            if max_batch is None:
                self.stdout.write("No Sites with batch_num found; nothing to run.")
                return  # success / nothing to do
            batches = list(range(0, int(max_batch) + 1))

        # Run the batches
        any_failure = False
        for batch_id in batches:
            self.stdout.write(f"Running ingest_batch for batch {batch_id} (run {new_run})...")
            try:
                # call_command blocks until ingest_batch returns (synchronous)
                call_command("ingest_batch", str(batch_id), str(new_run), days=days)
            except Exception as exc:
                any_failure = True
                err_msg = f"Batch {batch_id} failed for run {new_run}: {exc}"
                self.stderr.write(err_msg)
                # Record an error log row for visibility (best-effort)
                try:
                    Logging.objects.create(log_type="INGEST_ERROR", value=err_msg)
                except Exception as e:
                    self.stderr.write(f"Failed to write INGEST_ERROR log: {e}")
            else:
                self.stdout.write(f"Batch {batch_id} completed.")

        # Count how many Articles were written for this run and log completion
        try:
            loaded_count = Articles.objects.filter(run_id=new_run).count()
        except Exception as e:
            self.stderr.write(f"Failed to count articles for run {new_run}: {e}")
            loaded_count = 0

        complete_msg = f"Run:[{new_run}], Loaded [{loaded_count}] articles"
        try:
            Logging.objects.create(log_type="INGEST_COMPLETE", value=complete_msg)
        except Exception as e:
            self.stderr.write(f"Failed to write INGEST_COMPLETE log: {e}")

        self.stdout.write(complete_msg)

        #Call the count_articles script in mini mode
        try:
            self.stdout.write("Updating article counts for sites...")
            call_command("count_articles", "--mode", "mini")
            self.stdout.write("Article counts updated successfully.")
        except Exception as e:
            self.stderr.write(f"Failed to update article counts: {e}")


        # If any batch had an exception, raise CommandError -> non-zero exit code
        if any_failure:
            raise CommandError("One or more batches failed during ingest_all")
        # Otherwise return None (successful)
        return