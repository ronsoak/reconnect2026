# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Seed DB
#
# Populates the DB with set values to speed up deployment. 
#
# Command Examples
#   Default run: python manage.py seed_db
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management.base import BaseCommand
from django.db import transaction
from website.models import Logic
from website.seed_data import LOGIC

class Command(BaseCommand):
    help = "Populate the Logic table"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding Logic table...")

        for logic_type, values in LOGIC.items():
            for value in values:
                # Normalize/skip empty values if needed
                if value is None:
                    continue
                value_str = str(value).strip()
                if not value_str:
                    continue

                Logic.objects.update_or_create(
                    logic_type=logic_type,
                    value=value_str,
                )

        self.stdout.write(self.style.SUCCESS("Logic table seeded successfully."))