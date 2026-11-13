from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from website.models import Articles, Sites


class IngestAllTests(TestCase):
    def test_count_refresh_failure_raises_without_rolling_back_imported_articles(self):
        site = Sites.objects.create(
            name="Fixture", url="https://fixture.example.com",
            rss_feed="https://fixture.example.com/feed",
        )

        def run_child(command, *args, **kwargs):
            if command == "ingest_batch":
                Articles.objects.create(
                    site=site, title="Imported article", url="https://fixture.example.com/article",
                    run_id=int(args[1]),
                )
            elif command == "count_articles":
                raise RuntimeError("Count refresh unavailable")
            else:
                self.fail(f"Unexpected child command: {command}")

        with mock.patch(
            "website.management.commands.ingest_all.call_command", side_effect=run_child,
        ) as child:
            with self.assertRaisesMessage(CommandError, "article-count refresh failed"):
                call_command("ingest_all", batch=0, stdout=StringIO(), stderr=StringIO())
        self.assertTrue(Articles.objects.filter(title="Imported article", run_id=1).exists())
        child.assert_any_call("count_articles", "--mode", "mini")
