# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
# Import Sites
#
# Import or update sites from a CSV file.
#
# Command Examples
#   Normal:     python manage.py import_sites --file website/reconnect2026_test.csv
#   Dry Run:    python manage.py import_sites --file website/reconnect2026_test.csv --dry-run
#   1st Error:  python manage.py import_sites --file website/reconnect2026_test.csv --stop-on-first-error
#
# Optional column: recap (true/false). If the column is missing or a cell is blank,
# new sites default to true and existing sites are left unchanged.
#
# ===== ===== ===== ===== ===== ===== ===== ===== ===== =====
import csv

from django.core.management import BaseCommand, CommandError
from django.db import transaction

from website.models import Logic, Sites


def parse_bool(value):
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


class Command(BaseCommand):
    help = "Import sites from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True, help="Path to the CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and preview the import without writing to the database",
        )
        parser.add_argument(
            "--stop-on-first-error",
            action="store_true",
            help="Stop on the first invalid CSV row",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        dry_run = options["dry_run"]
        stop_on_first_error = options["stop_on_first_error"]
        required_columns = {
            "name",
            "url",
            "rss_feed",
            "site_type",
            "category",
            "tags",
            "bluesky",
            "modifier",
            "batch_num",
            "last_article",
            "hidden",
            "auto_post",
            "load_error",
            "description",
        }
        errors = 0
        created_count = 0
        updated_count = 0

        try:
            csv_file = open(file_path, newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"Could not open CSV file {file_path!r}: {exc}") from exc

        with csv_file:
            reader = csv.DictReader(csv_file)
            missing_columns = required_columns - set(reader.fieldnames or [])
            if missing_columns:
                raise CommandError(
                    "CSV is missing required column(s): "
                    + ", ".join(sorted(missing_columns))
                )

            self.stdout.write(f"Starting import from {file_path}...")

            for row_number, row in enumerate(reader, start=2):
                try:
                    site_type = Logic.objects.get(
                        logic_type="SITE_TYPE",
                        value=row["site_type"].strip(),
                    )
                    category = Logic.objects.get(
                        logic_type="CATEGORY",
                        value=row["category"].strip(),
                    )

                    tag_values = [
                        value.strip()
                        for value in row["tags"].split(";")
                        if value.strip()
                    ]
                    tags = [
                        Logic.objects.get(logic_type="TAG", value=value)
                        for value in tag_values
                    ]

                    site_url = row["url"].strip()
                    defaults = {
                        "name": row["name"].strip(),
                        "rss_feed": row["rss_feed"].strip(),
                        "site_type": site_type,
                        "category": category,
                        "bluesky": row["bluesky"].strip(),
                        "modifier": float(row["modifier"]),
                        "batch_num": int(row["batch_num"]),
                        "last_article": int(row["last_article"]),
                        "hidden": parse_bool(row["hidden"]),
                        "auto_post": parse_bool(row["auto_post"]),
                        "load_error": parse_bool(row["load_error"]),
                        "description": row["description"].strip(),
                    }

                    recap_value = (row.get("recap") or "").strip()
                    if recap_value:
                        defaults["recap"] = parse_bool(recap_value)

                    existing_site = Sites.objects.filter(url=site_url).first()
                    action = "Update" if existing_site else "Create"
                    self.stdout.write(
                        f"Row {row_number}: would {action.lower()} site "
                        f"{defaults['name']!r} ({site_url})"
                        if dry_run
                        else f"Row {row_number}: {action} site "
                        f"{defaults['name']!r} ({site_url})"
                    )

                    if dry_run:
                        continue

                    with transaction.atomic():
                        site, created = Sites.objects.update_or_create(
                            url=site_url,
                            defaults=defaults,
                        )
                        if tag_values:
                            site.tags.set(tags)

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as exc:
                    errors += 1
                    message = f"Error processing CSV row {row_number}: {exc}"
                    self.stderr.write(self.style.ERROR(message))
                    if stop_on_first_error:
                        raise CommandError(message) from exc

        summary = (
            f"Import finished: {created_count} created, {updated_count} updated, "
            f"{errors} row(s) with errors."
        )
        self.stdout.write(summary)

        if errors:
            raise CommandError(
                f"Import completed with {errors} row error(s); see errors above."
            )

        if dry_run:
            self.stdout.write("Dry run completed. No database changes were made.")
        else:
            self.stdout.write("Import completed successfully.")
