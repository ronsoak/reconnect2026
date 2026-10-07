import csv
import tempfile
from pathlib import Path
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.db.models.deletion import ProtectedError

from website.models import Articles, Logic, Sites


class ImportSitesCommandTests(TestCase):
    columns = [
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
    ]

    def setUp(self):
        self.site_type = Logic.objects.create(
            logic_type="SITE_TYPE",
            value="Website",
        )
        self.category = Logic.objects.create(
            logic_type="CATEGORY",
            value="Video Games",
        )
        self.old_tag = Logic.objects.create(logic_type="TAG", value="News")
        self.new_tag = Logic.objects.create(logic_type="TAG", value="Reviews")

    def make_row(self, **overrides):
        row = {
            "name": "Example Site",
            "url": "https://example.com",
            "rss_feed": "https://example.com/feed.xml",
            "site_type": "Website",
            "category": "Video Games",
            "tags": "Reviews",
            "bluesky": "",
            "modifier": "2.5",
            "batch_num": "3",
            "last_article": "4",
            "hidden": "false",
            "auto_post": "true",
            "load_error": "false",
            "description": "Updated description",
        }
        row.update(overrides)
        return row

    def run_import(self, row, **options):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "sites.csv"
            with file_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=self.columns)
                writer.writeheader()
                writer.writerow(row)

            output = StringIO()
            call_command(
                "import_sites",
                file=str(file_path),
                stdout=output,
                **options,
            )
            return output.getvalue()

    def test_dry_run_does_not_create_site_or_tags(self):
        output = self.run_import(self.make_row(), dry_run=True)

        self.assertEqual(Sites.objects.count(), 0)
        self.assertIn("would create site", output)
        self.assertIn("No database changes were made", output)

    def test_dry_run_does_not_update_existing_site(self):
        site = Sites.objects.create(
            name="Old Name",
            url="https://example.com",
            rss_feed="https://example.com/old-feed.xml",
            site_type=self.site_type,
            category=self.category,
            description="Old description",
        )
        site.tags.add(self.old_tag)

        self.run_import(self.make_row(), dry_run=True)

        site.refresh_from_db()
        self.assertEqual(site.name, "Old Name")
        self.assertEqual(site.rss_feed, "https://example.com/old-feed.xml")
        self.assertEqual(set(site.tags.all()), {self.old_tag})

    def test_import_updates_site_fields_and_tags(self):
        site = Sites.objects.create(
            name="Old Name",
            url="https://example.com",
            rss_feed="https://example.com/old-feed.xml",
            site_type=self.site_type,
            category=self.category,
            description="Old description",
        )
        site.tags.add(self.old_tag)

        self.run_import(self.make_row())

        site.refresh_from_db()
        self.assertEqual(site.name, "Example Site")
        self.assertEqual(site.rss_feed, "https://example.com/feed.xml")
        self.assertEqual(site.modifier, 2.5)
        self.assertEqual(set(site.tags.all()), {self.new_tag})
        self.assertEqual(Sites.objects.count(), 1)

    def test_blank_tags_leave_existing_tags_unchanged(self):
        site = Sites.objects.create(
            name="Old Name",
            url="https://example.com",
            rss_feed="https://example.com/old-feed.xml",
            site_type=self.site_type,
            category=self.category,
            description="Old description",
        )
        site.tags.add(self.old_tag)

        self.run_import(self.make_row(tags=""))

        self.assertEqual(set(site.tags.all()), {self.old_tag})
        site.refresh_from_db()
        self.assertEqual(site.name, "Example Site")


class ProtectedDeleteTests(TestCase):
    def test_site_taxonomy_cannot_be_deleted_while_referenced(self):
        site_type = Logic.objects.create(logic_type="SITE_TYPE", value="Website")
        category = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        site = Sites.objects.create(
            name="Example Site",
            url="https://example.com",
            rss_feed="https://example.com/feed.xml",
            site_type=site_type,
            category=category,
            description="A test publication",
        )
        article = Articles.objects.create(
            title="Example Article",
            url="https://example.com/article",
            image_url="",
            site=site,
        )

        with self.assertRaises(ProtectedError):
            category.delete()

        with self.assertRaises(ProtectedError):
            site.delete()

        self.assertTrue(Sites.objects.filter(pk=site.pk).exists())
        self.assertTrue(Articles.objects.filter(pk=article.pk).exists())


class ImportArticlesCommandTests(TestCase):
    def setUp(self):
        category = Logic.objects.create(
            logic_type="CATEGORY",
            value="Video Games",
        )
        self.site = Sites.objects.create(
            name="Example Site",
            url="https://example.com",
            rss_feed="https://example.com/feed.xml",
            category=category,
            description="A test publication",
        )
        self.article = Articles.objects.create(
            title="Original Title",
            url="https://example.com/article",
            image_url="https://example.com/image.jpg",
            site=self.site,
            run_id=9,
            clicks=7,
            boost=3,
            modifier=2,
            hidden=True,
            site_hide=True,
            manual_post=True,
            bluesky=True,
        )

    def run_import(self, row):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "articles.csv"
            with file_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)

            output = StringIO()
            call_command(
                "import_articles",
                str(file_path),
                stdout=output,
                stderr=StringIO(),
            )
            return output.getvalue()

    def test_blank_metrics_and_flags_preserve_existing_values(self):
        self.run_import(
            {
                "title": "Updated Title",
                "url": self.article.url,
                "site": self.site.name,
                "run_id": "",
                "clicks": "",
                "boost": "",
                "modifier": "",
                "hidden": "",
                "site_hide": "",
                "manual_post": "",
                "bluesky": "",
            }
        )

        self.article.refresh_from_db()
        self.assertEqual(self.article.title, "Updated Title")
        self.assertEqual(self.article.run_id, 9)
        self.assertEqual(self.article.clicks, 7)
        self.assertEqual(self.article.boost, 3)
        self.assertEqual(self.article.modifier, 2)
        self.assertTrue(self.article.hidden)
        self.assertTrue(self.article.site_hide)
        self.assertTrue(self.article.manual_post)
        self.assertTrue(self.article.bluesky)

    def test_explicit_metrics_and_flags_are_applied(self):
        self.run_import(
            {
                "title": "Updated Title",
                "url": self.article.url,
                "site": self.site.name,
                "clicks": "0",
                "boost": "1.5",
                "modifier": "3",
                "hidden": "false",
            }
        )

        self.article.refresh_from_db()
        self.assertEqual(self.article.clicks, 0)
        self.assertEqual(self.article.boost, 1.5)
        self.assertEqual(self.article.modifier, 3)
        self.assertFalse(self.article.hidden)
        self.assertEqual(self.article.run_id, 9)

    def test_invalid_numeric_value_fails_without_updating_article(self):
        with self.assertRaises(CommandError):
            self.run_import(
                {
                    "title": "Updated Title",
                    "url": self.article.url,
                    "site": self.site.name,
                    "clicks": "not-a-number",
                }
            )

        self.article.refresh_from_db()
        self.assertEqual(self.article.title, "Original Title")
        self.assertEqual(self.article.clicks, 7)
