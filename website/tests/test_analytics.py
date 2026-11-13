from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from website.management.commands.aggregate_clicks import next_month, parse_month, previous_month
from website.models import Adverts, Analytics, Articles, Clicks, Logging, Logic, Sites


class AggregateClicksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.advert_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Advert")
        cat = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.site = Sites.objects.create(
            name="Site", url="https://s.example.com", rss_feed="https://s.example.com/feed",
            description="x",
        )
        cls.site.categories.add(cat)

    def click(self, kind, object_id, day, site=None):
        Clicks.objects.create(type=kind, article=str(object_id), site=site, date=day)

    def run_command(self, *args):
        out = StringIO()
        with mock.patch(
            "website.management.commands.aggregate_clicks.timezone.localdate",
            return_value=date(2026, 1, 15),
        ):
            call_command("aggregate_clicks", *args, stdout=out)
        return out.getvalue()

    def make_baseline_objects(self):
        article = Articles.objects.create(
            title="Imported article", url="https://s.example.com/imported",
            image_url="", site=self.site, clicks=500, hidden=True, site_hide=True,
        )
        zero = Articles.objects.create(
            title="No clicks", url="https://s.example.com/zero",
            image_url="", site=self.site, clicks=0,
        )
        size = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        advert = Adverts.objects.create(
            title="Expired advert", message="Advert", site_url="https://advert.example.com",
            start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
            advert_size=size, clicks=12,
        )
        return article, zero, advert

    def test_baseline_snapshots_all_totals_into_previous_calendar_month(self):
        article, zero, advert = self.make_baseline_objects()
        self.click(self.article_type, article.pk, date(2025, 12, 1), self.site)
        self.run_command("--baseline")

        rows = Analytics.objects.filter(month=date(2025, 12, 1), is_baseline=True)
        self.assertEqual(rows.count(), 3)
        self.assertEqual(rows.get(type=self.article_type, object_id=article.pk).clicks, 500)
        self.assertEqual(rows.get(type=self.article_type, object_id=article.pk).site, self.site)
        self.assertEqual(rows.get(type=self.article_type, object_id=zero.pk).clicks, 0)
        self.assertEqual(rows.get(type=self.advert_type, object_id=advert.pk).clicks, 12)
        self.assertIsNone(rows.get(type=self.advert_type, object_id=advert.pk).site)
        article.refresh_from_db()
        advert.refresh_from_db()
        self.assertEqual((article.clicks, advert.clicks, Clicks.objects.count()), (500, 12, 1))
        self.assertTrue(Logging.objects.filter(value__contains="Baseline 2025-12").exists())

    def test_baseline_dry_run_writes_nothing(self):
        self.make_baseline_objects()
        output = self.run_command("--baseline", "--dry-run")
        self.assertIn("512 clicks", output)
        self.assertIn("Dry run", output)
        self.assertFalse(Analytics.objects.exists())
        self.assertFalse(Logging.objects.exists())

    def test_baseline_refuses_existing_analytics(self):
        self.make_baseline_objects()
        existing = Analytics.objects.create(
            type=self.article_type, object_id=999, month=date(2025, 12, 1), clicks=7,
        )
        with self.assertRaisesMessage(CommandError, "requires an empty month"):
            self.run_command("--baseline")
        existing.refresh_from_db()
        self.assertEqual((Analytics.objects.count(), existing.clicks), (1, 7))
        self.assertFalse(Logging.objects.exists())

    def test_baseline_cannot_be_overwritten_or_recaptured(self):
        article, _, _ = self.make_baseline_objects()
        self.run_command("--baseline")
        self.click(self.article_type, article.pk, date(2025, 12, 1), self.site)
        for args in (("--baseline",), ("--month", "2025-12")):
            with self.subTest(args=args), self.assertRaisesMessage(CommandError, "cannot be overwritten"):
                self.run_command(*args)
        with mock.patch(
            "website.management.commands.aggregate_clicks.timezone.localdate",
            return_value=date(2026, 2, 15),
        ), self.assertRaisesMessage(CommandError, "only be captured once"):
            call_command("aggregate_clicks", baseline=True, stdout=StringIO())
        self.assertEqual(
            Analytics.objects.get(type=self.article_type, object_id=article.pk).clicks, 500,
        )
        self.click(self.article_type, article.pk, date(2026, 1, 3), self.site)
        self.run_command("--month", "2026-01")
        monthly = Analytics.objects.get(month=date(2026, 1, 1))
        self.assertEqual(monthly.clicks, 1)
        self.assertFalse(monthly.is_baseline)

    def test_baseline_rejects_invalid_counts_without_partial_writes(self):
        article, _, advert = self.make_baseline_objects()
        for count in (-1, 1.5, float("inf")):
            Adverts.objects.filter(pk=advert.pk).update(clicks=count)
            with self.subTest(count=count), self.assertRaisesMessage(CommandError, "invalid baseline clicks"):
                self.run_command("--baseline")
            self.assertFalse(Analytics.objects.exists())
            self.assertFalse(Logging.objects.exists())

    def test_baseline_requires_seeded_types_and_imported_objects(self):
        with self.assertRaisesMessage(CommandError, "No articles or adverts"):
            self.run_command("--baseline")
        self.advert_type.delete()
        with self.assertRaisesMessage(CommandError, "Seed the Article and Advert"):
            self.run_command("--baseline")

    def test_baseline_cannot_select_another_month(self):
        with self.assertRaises(CommandError):
            self.run_command("--baseline", "--month", "2026-09")

    def test_month_helpers(self):
        self.assertEqual(parse_month("", date(2026, 1, 15)), date(2025, 12, 1))
        self.assertEqual(parse_month("current", date(2026, 3, 15)), date(2026, 3, 1))
        self.assertEqual(parse_month("2026-09", date(2026, 10, 8)), date(2026, 9, 1))
        self.assertEqual(next_month(date(2026, 12, 1)), date(2027, 1, 1))
        self.assertEqual(previous_month(date(2026, 3, 1)), date(2026, 2, 1))
        with self.assertRaises(CommandError):
            parse_month("September", date(2026, 10, 8))

    def test_totals_per_object_per_month_on_the_first(self):
        for day in (date(2026, 9, 1), date(2026, 9, 15), date(2026, 9, 30)):
            self.click(self.article_type, 7, day, self.site)
        self.click(self.advert_type, 7, date(2026, 9, 10))
        self.click(self.article_type, 7, date(2026, 10, 1), self.site)
        self.click(self.article_type, 7, date(2026, 8, 31), self.site)
        self.run_command("--month", "2026-09")

        article = Analytics.objects.get(type=self.article_type, object_id=7)
        self.assertEqual((article.month, article.clicks, article.site), (date(2026, 9, 1), 3, self.site))
        advert = Analytics.objects.get(type=self.advert_type, object_id=7)
        self.assertEqual((advert.clicks, advert.site), (1, None))
        self.assertEqual(Analytics.objects.count(), 2)

    def test_months_without_clicks_have_no_row(self):
        self.click(self.article_type, 7, date(2026, 9, 5), self.site)
        self.run_command("--month", "2026-09")
        self.run_command("--month", "2026-08")
        self.assertEqual(list(Analytics.objects.values_list("month", flat=True)), [date(2026, 9, 1)])

    def test_rerunning_does_not_double_count(self):
        self.click(self.article_type, 7, date(2026, 9, 5), self.site)
        self.run_command("--month", "2026-09")
        self.click(self.article_type, 7, date(2026, 9, 6), self.site)
        self.run_command("--month", "2026-09")
        self.assertEqual(Analytics.objects.get().clicks, 2)

    def test_purging_clicks_keeps_analytics_and_a_rerun_is_harmless(self):
        self.click(self.article_type, 7, date(2026, 9, 5), self.site)
        self.run_command("--month", "2026-09")
        Clicks.objects.all().delete()
        self.run_command("--month", "2026-09")
        self.assertEqual(Analytics.objects.get().clicks, 1)

    def test_dry_run_saves_nothing(self):
        self.click(self.article_type, 7, date(2026, 9, 5), self.site)
        output = self.run_command("--month", "2026-09", "--dry-run")
        self.assertIn("Dry run", output)
        self.assertEqual(Analytics.objects.count(), 0)
        self.assertEqual(Logging.objects.count(), 0)

    def test_untyped_and_non_numeric_rows_are_skipped_and_run_is_logged(self):
        Clicks.objects.create(type=None, article="7", date=date(2026, 9, 5))
        Clicks.objects.create(type=self.article_type, article="abc", date=date(2026, 9, 5))
        self.click(self.article_type, 8, date(2026, 9, 5), self.site)
        self.run_command("--month", "2026-09")
        self.assertEqual(list(Analytics.objects.values_list("object_id", flat=True)), [8])
        self.assertTrue(Logging.objects.filter(log_type="ANALYTICS_TASK").exists())

    def test_one_row_per_object_per_month_is_enforced(self):
        Analytics.objects.create(type=self.article_type, object_id=1, month=date(2026, 9, 1), clicks=1)
        with self.assertRaises(IntegrityError):
            Analytics.objects.create(type=self.article_type, object_id=1, month=date(2026, 9, 1), clicks=2)
