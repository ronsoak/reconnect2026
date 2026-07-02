# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Batch Sites Script
#
# Assigns a batch_num value to each of the active sites
# This is to break up ingest runs 
#
# Command Examples
#   Default run (batch size 20, active sites only): python manage.py batch_sites
#   Custom batch size (25 per batch): python manage.py batch_sites --batch-size 25
#   Use a seed for reproducible assignments: python manage.py batch_sites --seed 42
#   Include hidden sites as well (not recommended unless intended): python manage.py batch_sites --only-active=False (or modify call to not pass --only-active; the command defaults to only_active=True)
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management.base import BaseCommand
from django.db import transaction
from typing import Any, List, Optional
from website.models import Sites, Logging
import math
import random

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = "Batch active sites into groups (default size 20) and assign batch numbers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=20,
            help="Maximum sites per batch (default: 20).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            help="Optional random seed to produce repeatable batch assignments.",
        )
        parser.add_argument(
            "--only-active",
            action="store_true",
            help="Only include sites where hidden=False (default: include only active sites).",
        )

    def handle(self, *args: Any, **options: Any):
        batch_size: int = max(1, int(options.get("batch_size", 20)))
        seed: Optional[int] = options.get("seed")
        only_active: bool = options.get("only_active", True)

        # Select sites: active sites by default (hidden=False)
        qs = Sites.objects.all()
        if only_active:
            qs = qs.filter(hidden=False)

        site_list: List[Sites] = list(qs.order_by("pk"))
        total_sites = len(site_list)

        if total_sites == 0:
            self.stdout.write(self.style.WARNING("No sites found to batch."))
            # Still write a log entry if you prefer; here we create a log with 0 batches.
            try:
                Logging.objects.create(
                    log_type="BATCH_TASK",
                    value="Batching: 0 many batches have been assigned.",
                )
            except Exception as e:
                self.stderr.write(f"Failed to write Logging row: {e}")
            return

        if seed is not None:
            random.seed(seed)

        random.shuffle(site_list)

        # Assign batch numbers (0-based)
        assignments: List[Sites] = []
        for index, site in enumerate(site_list):
            batch_num = index // batch_size
            site.batch_num = batch_num
            assignments.append(site)

        num_batches = math.ceil(total_sites / batch_size)

        try:
            # Bulk update in a transaction
            with transaction.atomic():
                Sites.objects.bulk_update(assignments, ["batch_num"], batch_size=100)
        except Exception as exc:
            self.stderr.write(f"Failed to update Sites with batch_num: {exc}")
            return 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully batched {total_sites} sites into {num_batches} batches (batch_size={batch_size})."
            )
        )

        # Write a Logging record with the number of batches created
        try:
            Logging.objects.create(
                log_type="BATCH_TASK",
                value=f"Batching: [{num_batches}] many batches have been assigned.",
            )
            self.stdout.write("Logged BATCH_TASK entry.")
        except Exception as e:
            self.stderr.write(f"Failed to write Logging row: {e}")

        return 0