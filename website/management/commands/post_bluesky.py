"""Post at most one eligible article per invocation.

Examples:
    python manage.py post_bluesky --dry-run
    python manage.py post_bluesky

Schedule every 15 minutes: */15 * * * *
Set BLUESKY_IDENTIFIER and BLUESKY_APP_PASSWORD in the environment, never in code.
Dry-run needs no credentials, makes no network calls and changes no records.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from website.bluesky import BlueskyClient, BlueskyError, eligible_articles, new_record_key, post_text
from website.models import Articles


class Command(BaseCommand):
    help = "Post one public, unposted article within BLUESKY_LOOKBACK_DAYS, oldest first."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without network calls or writes.")

    def handle(self, *args, **options):
        article = eligible_articles().first()
        if article is None:
            self.stdout.write("No eligible articles to post.")
            return
        try:
            text, _ = post_text(article)
            if options["dry_run"]:
                self.stdout.write(json.dumps({
                    "article_id": article.pk, "text": text, "link": article.url,
                    "title": article.title, "image": article.image_url or "Local placeholder",
                    "image_fallback": "Stable local placeholder if the image is absent or unusable.",
                    "mention": "Resolved to a clickable mention during live posting." if article.site.bluesky else None,
                }, ensure_ascii=False, indent=2))
                return
            if not settings.BLUESKY_IDENTIFIER or not settings.BLUESKY_APP_PASSWORD:
                raise CommandError("Set BLUESKY_IDENTIFIER and BLUESKY_APP_PASSWORD before live posting.")

            # Commit the key before external side effects. Never allocate a new key on retry.
            with transaction.atomic():
                reserved = Articles.objects.select_for_update().get(pk=article.pk)
                if reserved.bluesky:
                    self.stdout.write("This article was posted by another run; nothing posted.")
                    return
                if not reserved.bluesky_rkey:
                    reserved.bluesky_rkey = new_record_key()
                    reserved.save(update_fields=["bluesky_rkey"])

            client = BlueskyClient(settings.BLUESKY_IDENTIFIER, settings.BLUESKY_APP_PASSWORD)
            try:
                # Serialize the same candidate on PostgreSQL. The remote record key also
                # prevents duplicates if a process dies after posting but before DB commit.
                with transaction.atomic():
                    locked = Articles.objects.select_for_update().get(pk=article.pk)
                    if locked.bluesky:
                        self.stdout.write("This article was posted by another run; nothing posted.")
                        return
                    current = eligible_articles().filter(pk=locked.pk).first()
                    if current is None:
                        self.stdout.write("Article eligibility changed; nothing posted.")
                        return
                    uri = client.publish(current, self.stderr.write)
                    locked.bluesky = True
                    locked.save(update_fields=["bluesky"])
            finally:
                client.close()
        except BlueskyError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Article {article.pk} posted/reconciled: {uri}"))
