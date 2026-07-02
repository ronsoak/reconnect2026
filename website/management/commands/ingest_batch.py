# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Ingest Batch
#
# Get articles for the sites in this batch
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
import feedparser
import requests
import traceback
from datetime import timedelta, datetime as _dt
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from interruptingcow import timeout
from requests.adapters import HTTPAdapter
from typing import Any, Optional
from urllib3.util.retry import Retry
from website.models import Sites, Articles, Logging

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
def build_requests_session(retries: int = 2, backoff: float = 0.5, user_agent: Optional[str] = None):
    s = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if user_agent:
        s.headers.update({"User-Agent": user_agent})
    return s


class Command(BaseCommand):
    help = "Ingest a batch of sites. Usage: manage.py ingest_batch <batch_num> <run_id> [--days N]"

    def add_arguments(self, parser):
        parser.add_argument("batch_num", type=int, help="Batch number to process (batches start at 0)")
        parser.add_argument("run_id", type=int, help="Run id to store on created Articles")
        parser.add_argument(
            "--days",
            type=int,
            default=14,
            help="How many days back to import (default: 14). Use a larger number to backfill.",
        )
        parser.add_argument(
            "--per-site-timeout",
            type=int,
            default=120,
            help="Max seconds to spend processing a single site (default: 120)",
        )
        parser.add_argument(
            "--request-timeout",
            type=float,
            default=10.0,
            help="Requests timeout (seconds) passed to requests.get (default: 10.0)",
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=2,
            help="Maximum number of retries for a problematic site (default: 2)",
        )
        parser.add_argument(
            "--user-agent",
            type=str,
            default="django-ingest-bot/1.0",
            help="User-Agent header for HTTP requests",
        )

    def handle(self, *args: Any, **options: Any):
        batch_num: int = options["batch_num"]
        run_id: int = options["run_id"]
        days: int = options["days"]
        per_site_timeout: int = options["per_site_timeout"]
        request_timeout: float = options["request_timeout"]
        max_retries: int = options["max_retries"]
        user_agent: Optional[str] = options.get("user_agent")

        date_cutoff = timezone.localdate() - timedelta(days=days)

        self.stdout.write(f"Starting ingest_batch batch={batch_num} run_id={run_id} days={days} cutoff={date_cutoff}")
        session = build_requests_session(retries=2, backoff=0.5, user_agent=user_agent)

        qs = Sites.objects.filter(batch_num=batch_num, load_error=False, hidden=False).order_by("id")
        total_sites = qs.count()
        if total_sites == 0:
            self.stdout.write(f"No sites found for batch {batch_num} (or all are hidden/errored).")
            return

        self.stdout.write(f"Found {total_sites} site(s) for batch {batch_num}.")

        for site in qs:
            site_name = site.name
            feed_url = (site.rss_feed or "").strip()
            self.stdout.write(f"--- Processing site {site_name!r} (id={site.pk}) feed={feed_url}")

            if not feed_url:
                msg = f"{site_name}: empty feed url"
                self.stderr.write(msg)
                Logging.objects.create(log_type="INGEST_ERROR", value=msg)
                site.load_error = True
                site.save(update_fields=["load_error"])
                continue

            attempt = 0
            success = False
            last_exc_text = ""
            total_attempts = 1 + max_retries
            for attempt in range(1, total_attempts + 1):
                try:
                    with timeout(per_site_timeout, exception=RuntimeError):
                        resp = session.get(feed_url, timeout=request_timeout, allow_redirects=True)
                        resp.raise_for_status()

                        feed = feedparser.parse(resp.content)

                        if getattr(feed, "bozo", 0):
                            bozo_exc = getattr(feed, "bozo_exception", None)
                            self.stderr.write(f"Warning: bozo flag set for {site_name}: {bozo_exc}")

                        entries = getattr(feed, "entries", []) or []
                        if not entries:
                            self.stdout.write(f"No entries found for {site_name}.")
                            success = True
                            break

                        entries_processed = 0
                        for entry in entries:
                            link = entry.get("link") or entry.get("id")
                            if not link:
                                continue

                            # Skip duplicates
                            if Articles.objects.filter(url=link).exists():
                                continue

                            title = (entry.get("title") or "").strip() or "Untitled"

                            # Parse publish date (best-effort)
                            pub_date = None
                            try:
                                if entry.get("published_parsed"):
                                    dt = entry.published_parsed
                                    pub_date = _dt(*dt[:6]).date()
                                elif entry.get("updated_parsed"):
                                    dt = entry.updated_parsed
                                    pub_date = _dt(*dt[:6]).date()
                            except Exception:
                                pub_date = None

                            if pub_date is None:
                                pub_date = timezone.localdate()

                            # If the article is older than or equal to cutoff, stop processing further entries (feeds are typically newest-first)
                            if pub_date <= date_cutoff:
                                self.stdout.write(
                                    f"Encountered entry older than cutoff ({pub_date}) for {site_name}; stopping further entries."
                                )
                                break

                            # Try to get an image preview (best-effort)
                            image_url = ""
                            try:
                                from linkpreview import link_preview

                                lp = link_preview(link, parser="lxml")
                                image_url = getattr(lp, "image", "") or ""
                            except Exception:
                                image_url = getattr(site, "logo", None)
                                if hasattr(image_url, "url"):
                                    image_url = image_url.url
                                if not image_url:
                                    image_url = ""

                            # Create the Article record
                            try:
                                with transaction.atomic():
                                    article, created = Articles.objects.get_or_create(
                                        url=link,
                                        defaults={
                                            "title": title[:255],
                                            "image_url": str(image_url)[:512] if image_url is not None else "",
                                            "site": site,
                                            "published": pub_date,
                                            "run_id": run_id,
                                        },
                                    )
                                    if created:
                                        entries_processed += 1
                                        self.stdout.write(f"Imported article: {title!r} ({link})")
                            except Exception as e:
                                self.stderr.write(f"Failed to create article for {link} on site {site_name}: {e}")
                                continue

                        self.stdout.write(f"Site {site_name} processed; new articles: {entries_processed}")
                        success = True
                        break

                except RuntimeError as e:
                    last_exc_text = f"Timeout after {per_site_timeout}s: {e}"
                    self.stderr.write(f"Attempt {attempt}/{total_attempts} for {site_name} timed out: {e}")
                except requests.exceptions.RequestException as e:
                    last_exc_text = f"HTTP error: {e}"
                    self.stderr.write(f"Attempt {attempt}/{total_attempts} for {site_name} HTTP error: {e}")
                except Exception as e:
                    last_exc_text = f"Unhandled error: {e}\n{traceback.format_exc()}"
                    self.stderr.write(f"Attempt {attempt}/{total_attempts} for {site_name} failed: {e}")

                if not success and attempt < total_attempts:
                    self.stdout.write(f"Retrying {site_name} (next attempt {attempt+1}/{total_attempts})...")

            if not success:
                err_value = f"{site_name}: {last_exc_text}"
                self.stderr.write(f"Marking site {site_name} as load_error due to: {last_exc_text}")
                site.load_error = True
                site.save(update_fields=["load_error"])
                try:
                    Logging.objects.create(log_type="INGEST_ERROR", value=err_value)
                except Exception as e:
                    self.stderr.write(f"Failed to write Logging row for site {site_name}: {e}")

        self.stdout.write(f"Finished ingest_batch batch={batch_num} run_id={run_id}")