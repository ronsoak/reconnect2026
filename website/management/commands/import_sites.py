# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Import Sites
#
# Used for importing sites from a CSV
#
# Command Examples
#   Normal:     python manage.py import_sites --file website/reconnect2026_test.csv
#   Dry Run:    python manage.py import_sites --file website/reconnect2026_test.csv --dry-run
#   1st Error:  python manage.py import_sites --file website/reconnect2026_test.csv --stop-on-first-error
#
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
import csv
from django.core.management import BaseCommand
from django.db import transaction
from website.models import Sites, Logic

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== =====
class Command(BaseCommand):
    help = 'Import sites from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to the CSV file')
        parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without saving changes')
        parser.add_argument('--stop-on-first-error', action='store_true', help='Stop on the first error encountered')

    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options['dry_run']
        stop_on_first_error = options['stop_on_first_error']

        try:
            with open(file_path, 'r') as file:
                reader = csv.DictReader(file)
                self.stdout.write(f"Starting import from {file_path}...")

                # Use a transaction to ensure atomicity
                with transaction.atomic():
                    for row in reader:
                        try:
                            # Lookup or create site_type
                            site_type = Logic.objects.get(logic_type='SITE_TYPE', value=row['site_type'])

                            # Lookup or create category
                            category = Logic.objects.get(logic_type='CATEGORY', value=row['category'])

                            # Lookup or create tags
                            tags = []
                            if row['tags']:
                                tag_values = [tag.strip() for tag in row['tags'].split(';')]
                                for tag_value in tag_values:
                                    tag = Logic.objects.get(logic_type='TAG', value=tag_value)
                                    tags.append(tag)

                            # Create or update the site
                            site, created = Sites.objects.get_or_create(
                                name=row['name'],
                                url=row['url'],
                                rss_feed=row['rss_feed'],
                                defaults={
                                    'site_type': site_type,
                                    'category': category,
                                    'bluesky': row['bluesky'],
                                    'modifier': float(row['modifier']),
                                    'batch_num': int(row['batch_num']),
                                    'last_article': int(row['last_article']),
                                    'hidden': row['hidden'].lower() == 'true',
                                    'auto_post': row['auto_post'].lower() == 'true',
                                    'load_error': row['load_error'].lower() == 'true',
                                    'description': row['description'],
                                }
                            )

                            # Add tags to the site
                            if created:
                                site.tags.set(tags)

                            # Save the site
                            if not dry_run:
                                site.save()

                            self.stdout.write(f"{'Created' if created else 'Updated'} site: {site.name}")

                        except Exception as e:
                            self.stderr.write(f"Error processing row: {row}")
                            self.stderr.write(str(e))
                            if stop_on_first_error:
                                raise e

                    if dry_run:
                        self.stdout.write("Dry run completed successfully. No changes were saved.")
                    else:
                        self.stdout.write("Import completed successfully.")

        except FileNotFoundError:
            self.stderr.write(f"File not found: {file_path}")
        except Exception as e:
            self.stderr.write(f"An unexpected error occurred: {e}")