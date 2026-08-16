# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Import Articles
#
# Used for importing articles from a CSV.
#
# Command Examples
#   Dry Run: python manage.py import_articles data/articles.csv --dry-run
#   Normal: python manage.py import_articles data/articles.csv 
#   Stop on first error: python manage.py import_articles data/articles.csv --stop-on-error
#   Match first site: python manage.py import_articles data/articles.csv --first-match
#
#CSV column suggestions (case-insensitive names):
#  title, url, image_url, published, created, run_id, boost, clicks, modifier,
#  hidden, site_hide, manual_post, bluesky, site
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from __future__ import annotations
from datetime import datetime
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from typing import Any, Dict, Iterable, Optional
import csv
import sys


def detect_field_to_match(model, candidate_fields=("name", "title", "site", "site_name")):
    fields = {f.name for f in model._meta.get_fields()}
    for c in candidate_fields:
        if c in fields:
            return c
    # fallback to first CharField/TextField-like name if present
    for f in model._meta.get_fields():
        try:
            it = f.get_internal_type()
        except Exception:
            it = ""
        if it in ("CharField", "TextField"):
            return f.name
    return None


def parse_bool(value: Any) -> bool:
    if value is None:
        return False
    v = str(value).strip().lower()
    if v in ("1", "true", "t", "yes", "y", "on"):
        return True
    if v in ("0", "false", "f", "no", "n", "off", ""):
        return False
    return False


def parse_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).strip()))
    except Exception:
        return default


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(str(value).strip())
    except Exception:
        return default


def parse_date(value: Any) -> Optional[datetime.date]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # try ISO first
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        pass
    # common formats
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    # last resort, try datetime parse
    try:
        parsed = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return parsed.date()
    except Exception:
        return None


class Command(BaseCommand):
    help = "Import Articles from CSV into website.Articles"

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to CSV file containing article data")
        parser.add_argument(
            "--site",
            help="Global site text to match against website.Sites (used if row doesn't provide site)",
            dest="site_text",
        )
        parser.add_argument("--dry-run", action="store_true", help="Do not write to the database; show what would be done")
        parser.add_argument(
            "--stop-on-error",
            action="store_true",
            help="Stop the import immediately on the first error and exit non-zero",
        )
        parser.add_argument(
            "--first-match",
            action="store_true",
            help="If site text matches multiple Site rows, pick the first match instead of failing",
        )
        parser.add_argument("--preview", action="store_true", help="Show a brief summary of the discovered models and exit")

    def handle(self, *args, **options):
        source = options["source"]
        dry_run: bool = options["dry_run"]
        stop_on_error: bool = options["stop_on_error"]
        global_site_text: Optional[str] = options.get("site_text")
        first_match_boolean: bool = options.get("first_match", False)
        preview = options.get("preview", False)

        # Explicit model references per your request
        try:
            Sites = apps.get_model("website", "Sites")
            Articles = apps.get_model("website", "Articles")
        except LookupError as e:
            raise CommandError("Could not find website.Sites and/or website.Articles models: %s" % e)

        site_match_field = detect_field_to_match(Sites)
        if site_match_field is None:
            raise CommandError("Unable to find a text field on the website.Sites model to match against.")

        if preview:
            self.stdout.write(self.style.SUCCESS("Preview mode:"))
            self.stdout.write(f"  Articles model: {Articles._meta.label}")
            self.stdout.write(f"  Sites model:    {Sites._meta.label}")
            self.stdout.write(f"  Site match field: {site_match_field}")
            self.stdout.write("Exit (preview).")
            return

        # Load CSV only
        try:
            with open(source, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
        except Exception as e:
            raise CommandError(f"Failed to open/read CSV source file {source}: {e}")

        total = 0
        created = 0
        updated = 0
        errors = 0

        for idx, raw in enumerate(rows, start=1):
            total += 1
            try:
                # Normalize keys to lower-case for convenience
                row = {k.strip().lower(): (v if v is not None else "") for k, v in raw.items()}

                title = row.get("title") or row.get("headline") or ""
                url = row.get("url") or row.get("link") or ""
                if not url:
                    raise ValueError(f"Row {idx}: missing required 'url' field")

                image_url = row.get("image_url") or row.get("image") or row.get("imageurl") or ""
                published = parse_date(row.get("published") or row.get("publish_date") or None)
                run_id = parse_int(row.get("run_id"), default=0)
                boost = parse_float(row.get("boost"), default=0.0)
                clicks = parse_float(row.get("clicks"), default=0.0)
                modifier = parse_float(row.get("modifier"), default=1.0)
                # boolean flags
                hidden = parse_bool(row.get("hidden"))
                site_hide = parse_bool(row.get("site_hide"))
                manual_post = parse_bool(row.get("manual_post"))
                bluesky = parse_bool(row.get("bluesky"))
                created_field = None
                created_raw = row.get("created")
                if created_raw:
                    try:
                        created_dt = datetime.fromisoformat(created_raw)
                        created_field = timezone.make_aware(created_dt) if created_dt.tzinfo is None else created_dt
                    except Exception:
                        created_field = None

                # Resolve site:
                site_text = (row.get("site") or global_site_text or "").strip()
                site_obj = None
                if site_text:
                    qs = Sites.objects.filter(**{f"{site_match_field}__iexact": site_text})
                    if qs.count() == 0:
                        qs = Sites.objects.filter(**{f"{site_match_field}__icontains": site_text})
                    cnt = qs.count()
                    if cnt == 1:
                        site_obj = qs.first()
                    elif cnt > 1:
                        if first_match_boolean:
                            site_obj = qs.first()
                        else:
                            raise ValueError(
                                f"Row {idx}: site text '{site_text}' matched multiple Sites ({cnt}); use --first-match to pick the first, or disambiguate your site text"
                            )
                    else:
                        raise ValueError(f"Row {idx}: no Site found matching '{site_text}' (field {site_match_field})")
                else:
                    raise ValueError(f"Row {idx}: no site provided in row and no --site supplied")

                defaults: Dict[str, Any] = {
                    "title": title,
                    "image_url": image_url,
                    "published": published,
                    "run_id": run_id,
                    "boost": boost,
                    "clicks": clicks,
                    "modifier": modifier,
                    "hidden": hidden,
                    "site_hide": site_hide,
                    "manual_post": manual_post,
                    "bluesky": bluesky,
                    "site": site_obj,
                }
                if created_field is not None:
                    defaults["created"] = created_field

                self.stdout.write(f"[{idx}/{total}] url={url} site={getattr(site_obj, site_match_field)} dry_run={dry_run}")

                if dry_run:
                    continue

                with transaction.atomic():
                    obj, was_created = Articles.objects.update_or_create(url=url, defaults=defaults)
                    if was_created:
                        created += 1
                    else:
                        updated += 1

            except Exception as e:
                errors += 1
                self.stderr.write(self.style.ERROR(f"Error processing row {idx}: {e}"))
                if stop_on_error:
                    self.stderr.write(self.style.ERROR("Stopping on first error (--stop-on-error)."))
                    raise CommandError("Stopped on first error")
                else:
                    continue

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import summary:"))
        self.stdout.write(f"  Total rows processed: {total}")
        if dry_run:
            self.stdout.write("  Dry-run mode (no DB writes performed).")
        else:
            self.stdout.write(f"  Created: {created}")
            self.stdout.write(f"  Updated: {updated}")
        self.stdout.write(f"  Errors: {errors}")