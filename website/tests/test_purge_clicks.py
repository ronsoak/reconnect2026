from datetime import date
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from website.management.commands.purge_clicks import newest_purgeable_month
from website.models import Analytics, Clicks, Logging, Logic

TODAY = date(2026, 10, 8)


class PurgeClicksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.kind = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")

    def click(self, day, object_id=1, kind=True):
        Clicks.objects.create(type=self.kind if kind else None, article=str(object_id), date=day)

    def run_command(self, *args):
        out = StringIO()
        with mock.patch("website.management.commands.purge_clicks.timezone.localdate", return_value=TODAY):
            call_command("purge_clicks", *args, stdout=out)
        return out.getvalue()

    def aggregate(self, month, clicks, object_id=1):
        Analytics.objects.create(type=self.kind, object_id=object_id, month=month, clicks=clicks)

    def test_newest_purgeable_month_is_four_back(self):
        self.assertEqual(newest_purgeable_month(TODAY), date(2026, 6, 1))
        self.assertEqual(newest_purgeable_month(date(2026, 2, 3)), date(2025, 10, 1))

    def test_deletes_only_the_month_four_back(self):
        for day in (date(2026, 5, 31), date(2026, 6, 1), date(2026, 6, 30), date(2026, 7, 1)):
            self.click(day)
        self.aggregate(date(2026, 6, 1), 2)
        self.run_command()
        self.assertEqual(sorted(Clicks.objects.values_list("date", flat=True)), [date(2026, 5, 31), date(2026, 7, 1)])
        self.assertEqual(Analytics.objects.count(), 1)
        self.assertTrue(Logging.objects.filter(log_type="ANALYTICS_TASK", value__contains="Purged 2").exists())

    def test_refuses_when_analytics_is_missing_or_different(self):
        self.click(date(2026, 6, 10))
        with self.assertRaises(CommandError):
            self.run_command()
        self.aggregate(date(2026, 6, 1), 5)
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertEqual(Clicks.objects.count(), 1)

    def test_force_overrides_the_check(self):
        self.click(date(2026, 6, 10), kind=False)
        self.run_command("--force")
        self.assertEqual(Clicks.objects.count(), 0)

    def test_recent_months_are_refused(self):
        self.click(date(2026, 7, 10))
        self.aggregate(date(2026, 7, 1), 1)
        with self.assertRaises(CommandError):
            self.run_command("--month", "2026-07")
        self.assertEqual(Clicks.objects.count(), 1)

    def test_older_month_can_be_purged(self):
        self.click(date(2026, 4, 2))
        self.aggregate(date(2026, 4, 1), 1)
        self.run_command("--month", "2026-04")
        self.assertEqual(Clicks.objects.count(), 0)

    def test_dry_run_deletes_nothing(self):
        self.click(date(2026, 6, 10))
        self.aggregate(date(2026, 6, 1), 1)
        self.assertIn("Dry run", self.run_command("--dry-run"))
        self.assertEqual(Clicks.objects.count(), 1)
