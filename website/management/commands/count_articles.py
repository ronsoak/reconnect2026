# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Count Articles
#
# Used to update article count value.
#
# Command Examples
#   Full: python manage.py count_articles --mode full
#   Mini: python manage.py count_articles --mode mini
#
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from website.models import Sites, Articles, Logging
from django.db.models import F


class Command(BaseCommand):
    help = "Updates the article_count field in the Sites model. Supports 'full' and 'mini' modes."

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['full', 'mini'],
            required=True,
            help="Specify the mode: 'full' for a complete count, 'mini' for an incremental update."
        )

    def handle(self, *args, **options):
        mode = options['mode']

        if mode == 'full':
            self.run_full_count()
        elif mode == 'mini':
            self.run_mini_count()
        else:
            raise CommandError("Invalid mode. Use 'full' or 'mini'.")

    def run_full_count(self):
        """
        Full count: Recalculate the total number of articles for each site and overwrite the article_count field.
        """
        self.stdout.write("Running full article count...")

        # Perform a full count of articles per site
        site_counts = Articles.objects.values('site').annotate(article_count=Count('id'))

        # Update the article_count field for each site
        for site_count in site_counts:
            site_id = site_count['site']
            count = site_count['article_count']
            Sites.objects.filter(id=site_id).update(article_count=count)

        # Log the execution
        Logging.objects.create(
            log_type='COUNT_ARTICLES',
            value='Article Count Full Executed'
        )

        self.stdout.write("Full article count completed successfully.")

    def run_mini_count(self):
        """
        Mini count: Incrementally update the article_count field based on the latest ingest run.
        """
        self.stdout.write("Running mini article count...")

        # Get the latest INGEST_RUN_ID from the Logging model
        latest_run_log = Logging.objects.filter(log_type='INGEST_RUN_ID').order_by('-created').first()
        if not latest_run_log:
            raise CommandError("No INGEST_RUN_ID found in Logging model.")

        try:
            latest_run_id = int(latest_run_log.value)
        except ValueError:
            raise CommandError(f"Invalid INGEST_RUN_ID value: {latest_run_log.value}")

        # Perform an incremental count of articles for the latest run, grouped by site
        site_counts = Articles.objects.filter(run_id=latest_run_id).values('site').annotate(article_count=Count('id'))

        # Incrementally update the article_count field for each site
        for site_count in site_counts:
            site_id = site_count['site']
            count = site_count['article_count']
            Sites.objects.filter(id=site_id).update(article_count=F('article_count') + count)

        # Log the execution
        Logging.objects.create(
            log_type='COUNT_ARTICLES',
            value='Article Count Mini Executed'
        )

        self.stdout.write("Mini article count completed successfully.")