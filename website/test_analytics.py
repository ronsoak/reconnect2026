from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from website.management.commands.aggregate_clicks import next_month, parse_month, previous_month
from website.models import Analytics, Clicks, Logging, Logic, Sites


class AggregateClicksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.advert_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Advert")
        cat = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.site = Sites.objects.create(
            name="Site", url="https://s.example.com", rss_feed="https://s.example.com/feed",
            category=cat, description="x",
        )

    def click(self, kind, object_id, day, site=None):
        Clicks.objects.create(type=kind, article=str(object_id), site=site, date=day)

    def run_command(self, *args):
        out = StringIO()
        call_command("aggregate_clicks", *args, stdout=out)
        return out.getvalue()

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
