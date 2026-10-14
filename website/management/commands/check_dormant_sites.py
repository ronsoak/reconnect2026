"""Check hidden, dormant publications for new dated feed entries.

Examples:
    python manage.py check_dormant_sites --dry-run
    python manage.py check_dormant_sites --site 5
    python manage.py check_dormant_sites --limit 10 --request-timeout 15

This checks RSS only; the next ingest run downloads the missing articles.
"""

from datetime import datetime
import math

import feedparser
import requests
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from website.models import Logging, Sites
from website.safe_fetch import UnsafeURL, build_safe_session, fetch


class Command(BaseCommand):
    help = "Reactivate hidden dormant sites whose RSS feed has a newer dated entry."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Check feeds without database writes.")
        parser.add_argument("--site", type=int, help="Check only this hidden dormant site.")
        parser.add_argument("--limit", type=int, default=0, help="Maximum sites to check (0 = all).")
        parser.add_argument("--request-timeout", type=float, default=10, help="HTTP timeout in seconds.")

    def handle(self, *args, **options):
        limit = options["limit"]
        request_timeout = options["request_timeout"]
        dry_run = options["dry_run"]
        if limit < 0:
            raise CommandError("--limit must be non-negative.")
        if not math.isfinite(request_timeout) or request_timeout <= 0:
            raise CommandError("--request-timeout must be a finite positive number.")

        sites = Sites.objects.filter(hidden=True, dormant=True).annotate(
            latest_published=Max("articles__published"),
        ).order_by("pk")
        if options["site"] is not None:
            sites = sites.filter(pk=options["site"])
        if limit:
            sites = sites[:limit]

        checked = recovered = errors = 0
        with build_safe_session(user_agent="reconnect-dormant-check/1.0") as session:
            for site in sites.iterator():
                checked += 1
                try:
                    content, _ = fetch(session, site.rss_feed, timeout=request_timeout)
                except (UnsafeURL, requests.RequestException) as exc:
                    errors += 1
                    message = f"Site {site.pk} '{site.name}': feed check failed: {exc}"
                    self.stderr.write(message)
                    if not dry_run:
                        Logging.objects.create(log_type="DORMANT_CHECK_TASK", value=message)
                    continue

                feed = feedparser.parse(content)
                if feed.get("bozo"):
                    self.stderr.write(
                        f"Site {site.pk} '{site.name}': feed parse warning: {feed.get('bozo_exception')}"
                    )

                # Match ingest's date precision, but never invent today's date for an undated entry.
                dates = []
                for entry in feed.get("entries", []):
                    if not (entry.get("link") or entry.get("id")):
                        continue
                    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                    if parsed:
                        try:
                            dates.append(datetime(*parsed[:6]).date())
                        except (TypeError, ValueError, OverflowError) as exc:
                            self.stderr.write(f"Site {site.pk}: invalid entry date: {exc}")
                if not dates:
                    self.stderr.write(f"Site {site.pk} '{site.name}': no usable dated entries; left dormant.")
                    continue
                latest_feed_date = max(dates)
                if site.latest_published is not None and latest_feed_date <= site.latest_published:
                    self.stdout.write(f"Site {site.pk} '{site.name}': no newer entries; left dormant.")
                    continue

                if dry_run:
                    recovered += 1
                    self.stdout.write(f"Would reactivate site {site.pk} '{site.name}' ({latest_feed_date}).")
                    continue

                # Recheck eligibility after the network request so a manual exclusion wins.
                with transaction.atomic():
                    updated = Sites.objects.filter(
                        pk=site.pk, hidden=True, dormant=True, rss_feed=site.rss_feed,
                    ).update(hidden=False, dormant=False, load_error=False)
                    if updated:
                        call_command("hide_articles", site=site.pk, stdout=self.stdout, stderr=self.stderr)
                if updated:
                    recovered += 1
                    self.stdout.write(f"Reactivated site {site.pk} '{site.name}' ({latest_feed_date}).")
                else:
                    self.stdout.write(f"Site {site.pk}: eligibility changed during check; skipped.")

        summary = (
            f"Checked {checked} dormant site(s); "
            f"{'would reactivate' if dry_run else 'reactivated'} {recovered}; fetch errors {errors}."
        )
        self.stdout.write(summary)
        if not dry_run:
            Logging.objects.create(log_type="DORMANT_CHECK_TASK", value=summary)
        if errors:
            raise CommandError("Some dormant feeds could not be checked; see errors above.")
