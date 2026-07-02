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
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from typing import Any, Optional
from website.models import Sites, Logging, Articles

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
        try:
            with transaction.atomic():
                log_entry = Logging.objects.select_for_update().filter(log_type="INGEST_RUN_ID").first()
                if log_entry is None:
                    log_entry = Logging.objects.create(log_type="INGEST_RUN_ID", defaults={"value": "0"})  # create initial
                try:
                    current_run = int(log_entry.value)
                except (TypeError, ValueError):
                    current_run = 0
                new_run = current_run + 1
                # Persist the reserved run id
                log_entry.value = str(new_run)
                log_entry.save(update_fields=["value"])
        except Exception as exc:
            self.stderr.write(f"Failed to reserve INGEST_RUN_ID: {exc}")
            return 1

        self.stdout.write(f"Reserved run id {new_run} (previous {current_run}). days={days}")

        # Determine batches to run
        batches = []
        if single_batch is not None:
            batches = [single_batch]
        else:
            agg = Sites.objects.aggregate(max_batch=Max("batch_num"))
            max_batch = agg.get("max_batch")
            if max_batch is None:
                self.stdout.write("No Sites with batch_num found; nothing to run.")
                return
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
                # Record an error log row for visibility
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

        # Return non-zero if any batch had an exception
        return 1 if any_failure else 0