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

            if logic_type == "CATEGORY":

                for category_name, tags in values.items():

                    category, _ = Logic.objects.update_or_create(
                        logic_type="CATEGORY",
                        value=category_name,
                        parent=None,
                    )

                    for tag in tags:

                        Logic.objects.update_or_create(
                            logic_type="TAG",
                            value=tag,
                            parent=category,
                        )

            else:

                for value in values:

                    Logic.objects.update_or_create(
                        logic_type=logic_type,
                        value=value,
                        parent=None,
                    )

        self.stdout.write(self.style.SUCCESS("Logic table seeded successfully."))