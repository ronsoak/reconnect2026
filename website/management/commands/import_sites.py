# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Import Sites
#
# Used for importing sites from a csv
#
# Command Examples
#   Dry Run: python manage.py import_sites reconnect2026_test.csv --dry-run
#   Normal: python manage.py import_sites reconnect2026_test.csv
#   Stop on first error: python manage.py import_sites reconnect2026_test.csv --stop-on-error
#
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError
from typing import List
from website.models import Sites, Logic
import csv

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== =====
def parse_bool(value: str) -> bool:
    if value is None:
        return False
    v = str(value).strip()
    if v == '':
        return False
    return v.lower() in ("true", "t", "yes", "y", "1")


def parse_float(value, default=0.0):
    if value is None or str(value).strip() == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_int(value, default=0):
    if value is None or str(value).strip() == '':
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


class Command(BaseCommand):
    help = "Import sites from a CSV and link site_type, category and tags (no auto-creation of Logic rows)."

    def add_arguments(self, parser):
        parser.add_argument("csvfile", type=str, help="Path to CSV file")
        parser.add_argument(
            "--tag-sep",
            dest="tag_sep",
            type=str,
            default=";",
            help="Separator used inside the tags field (default ';'). Use ',' only if tags field is properly quoted in CSV.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Do not persist changes (transaction will be rolled back at the end).",
        )
        parser.add_argument(
            "--stop-on-error",
            action="store_true",
            dest="stop_on_error",
            help="Stop the import when a row produces an error (default: continue and report).",
        )

    def handle(self, *args, **options):
        csvfile = options["csvfile"]
        tag_sep = options["tag_sep"]
        dry_run = options["dry_run"]
        stop_on_error = options["stop_on_error"]

        # Try to open the file
        try:
            fh = open(csvfile, newline='', encoding='utf-8')
        except OSError as e:
            raise CommandError(f"Cannot open CSV file: {e}")

        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise CommandError("CSV file has no header row or is empty.")

        # Standardize header names (strip)
        fieldnames = [f.strip() for f in reader.fieldnames]

        created = 0
        updated = 0
        errors = []

        # Wrap whole import so dry-run can rollback at the end
        with transaction.atomic():
            for rownum, raw_row in enumerate(reader, start=2):
                # Normalize the row keys and trim string values
                row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}

                name = row.get("name")
                url = row.get("url")
                rss_feed = row.get("rss_feed")
                site_type_val = row.get("site_type")
                category_val = row.get("category")
                tags_field = row.get("tags") or ""
                bluesky = row.get("bluesky") or ""
                modifier = parse_float(row.get("modifier"), default=2.0)
                last_article = parse_int(row.get("last_article"), default=0)
                batch_num = parse_int(row.get("batch_num"), default=0)
                hidden = parse_bool(row.get("hidden"))
                auto_post = parse_bool(row.get("auto_post"))
                load_error = parse_bool(row.get("load_error"))
                description = row.get("description") or ""

                if not name or not url:
                    msg = f"Row {rownum}: missing required 'name' or 'url' - skipping"
                    self.stdout.write(self.style.ERROR(msg))
                    errors.append(msg)
                    if stop_on_error:
                        break
                    continue

                try:
                    # Look up category (required)
                    category_obj = None
                    if category_val:
                        category_obj = Logic.objects.filter(logic_type="CATEGORY", value__iexact=category_val.strip()).first()
                        if not category_obj:
                            raise ValueError(f"CATEGORY '{category_val}' not found")

                    # Look up site_type (optional)
                    site_type_obj = None
                    if site_type_val:
                        site_type_obj = Logic.objects.filter(logic_type="SITE_TYPE", value__iexact=site_type_val.strip()).first()
                        if not site_type_obj:
                            raise ValueError(f"SITE_TYPE '{site_type_val}' not found")

                    # Parse tags using configured separator; allow empty list
                    tag_names: List[str]
                    if tags_field == "":
                        tag_names = []
                    else:
                        # If tag_sep is ',' and the CSV field was quoted like "Commentary, Industry",
                        # csv.DictReader would already give the whole string "Commentary, Industry".
                        # Splitting by tag_sep will then produce two tags; if you want that behavior
                        # you can set tag_sep=','; default is ';' to avoid ambiguity.
                        tag_names = [t.strip() for t in tags_field.split(tag_sep) if t.strip()]

                    tag_objs = []
                    for tag_name in tag_names:
                        if category_obj:
                            tag_obj = Logic.objects.filter(logic_type="TAG", value__iexact=tag_name, parent=category_obj).first()
                        else:
                            tag_obj = Logic.objects.filter(logic_type="TAG", value__iexact=tag_name).first()
                        if not tag_obj:
                            raise ValueError(f"TAG '{tag_name}' not found (category='{category_val}')")
                        tag_objs.append(tag_obj)

                    # Create or update site using unique url
                    site_obj = Sites.objects.filter(url=url).first()
                    if site_obj:
                        site_obj.name = name
                        site_obj.rss_feed = rss_feed
                        site_obj.site_type = site_type_obj
                        site_obj.category = category_obj
                        site_obj.bluesky = bluesky
                        site_obj.modifier = modifier
                        site_obj.last_article = last_article
                        site_obj.batch_num = batch_num
                        site_obj.hidden = hidden
                        site_obj.auto_post = auto_post
                        site_obj.load_error = load_error
                        site_obj.description = description
                        site_obj.save()
                        if tag_objs:
                            site_obj.tags.set(tag_objs)
                        else:
                            site_obj.tags.clear()
                        # Validate via model.clean (your clean checks tag/category consistency)
                        try:
                            site_obj.clean()
                        except ValidationError as ve:
                            raise ValueError(f"Validation after setting tags: {ve}")
                        updated += 1
                        self.stdout.write(self.style.SUCCESS(f"Row {rownum}: updated site {url}"))
                    else:
                        site_obj = Sites(
                            name=name,
                            url=url,
                            rss_feed=rss_feed,
                            site_type=site_type_obj,
                            category=category_obj,
                            bluesky=bluesky,
                            modifier=modifier,
                            last_article=last_article,
                            batch_num=batch_num,
                            hidden=hidden,
                            auto_post=auto_post,
                            load_error=load_error,
                            description=description,
                        )
                        site_obj.save()  # must save before M2M
                        if tag_objs:
                            site_obj.tags.set(tag_objs)
                        # Run model.clean to validate M2M vs category (your clean expects saved instance)
                        try:
                            site_obj.clean()
                        except ValidationError as ve:
                            raise ValueError(f"Validation after setting tags: {ve}")
                        created += 1
                        self.stdout.write(self.style.SUCCESS(f"Row {rownum}: created site {url}"))

                except (ValueError, IntegrityError) as e:
                    msg = f"Row {rownum}: ERROR: {e}"
                    self.stdout.write(self.style.ERROR(msg))
                    errors.append(msg)
                    if stop_on_error:
                        break
                    continue
                except Exception as e:
                    msg = f"Row {rownum}: Unexpected error: {e}"
                    self.stdout.write(self.style.ERROR(msg))
                    errors.append(msg)
                    if stop_on_error:
                        break
                    continue

            # End for rows

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry-run: rolled back all DB changes."))

        # Summary
        self.stdout.write(self.style.SUCCESS(f"Import complete: created={created}, updated={updated}, errors={len(errors)}"))
        if errors:
            self.stdout.write(self.style.ERROR("Errors:"))
            for e in errors:
                self.stdout.write(self.style.ERROR(f" - {e}"))