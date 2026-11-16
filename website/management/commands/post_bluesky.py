"""Make at most one Bluesky post: a due scheduled post first, otherwise an article.

Scheduled posts are managed in admin (Scheduled posts). Each goes out once on each
selected day, on the first run at or after its post time, and is skipped for that
day if it is more than BLUESKY_SCHEDULE_GRACE_MINUTES late. Otherwise the oldest
eligible article within BLUESKY_LOOKBACK_DAYS is posted.

Examples:
    python manage.py post_bluesky --dry-run
    python manage.py post_bluesky
    python manage.py post_bluesky --only scheduled
    python manage.py post_bluesky --only articles --dry-run

Schedule every 15 minutes: */15 * * * *
Set BLUESKY_IDENTIFIER (the account handle) and BLUESKY_APP_PASSWORD in the
environment, never in code. The login is stored encrypted in the database and
refreshed between runs, so the password is only used when no valid session exists.
Dry-run needs no credentials, makes no network calls and changes no records.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from website.bluesky import (
    BlueskyClient, BlueskyError, due_scheduled_posts, eligible_articles,
    new_record_key, post_text, scheduled_post_facets,
)
from website.models import Articles, ScheduledPost, ScheduledPostRun


class Command(BaseCommand):
    help = "Post one due scheduled post, or otherwise one eligible article, to Bluesky."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without network calls or writes.")
        parser.add_argument(
            "--only", choices=("all", "scheduled", "articles"), default="all",
            help="Limit this run to scheduled posts or articles (default: all).",
        )

    def handle(self, *args, **options):
        only = options["only"]
        due = due_scheduled_posts() if only != "articles" else []
        article = eligible_articles().first() if only != "scheduled" else None
        if not due and article is None:
            self.stdout.write("Nothing to post.")
            return
        if options["dry_run"]:
            self.preview(due, article)
            return
        if not settings.BLUESKY_IDENTIFIER or not settings.BLUESKY_APP_PASSWORD:
            raise CommandError("Set BLUESKY_IDENTIFIER and BLUESKY_APP_PASSWORD before live posting.")

        failures = []
        try:
            client = BlueskyClient(settings.BLUESKY_IDENTIFIER, settings.BLUESKY_APP_PASSWORD, self.stderr.write)
        except BlueskyError as exc:
            raise CommandError(str(exc)) from exc
        try:
            self.stdout.write(f"Bluesky session {client.session_source}.")
            if due:
                post, day = due[0]
                try:
                    if self.post_scheduled(client, post, day):
                        return
                except BlueskyError as exc:
                    ScheduledPostRun.objects.filter(scheduled_post=post, date=day).update(error=str(exc)[:500])
                    failures.append(f"Scheduled post '{post.name}': {exc}")
            if article is not None:
                try:
                    self.post_article(client, article)
                except BlueskyError as exc:
                    failures.append(f"Article {article.pk}: {exc}")
        finally:
            client.close()
        if failures:
            raise CommandError(" ".join(failures))

    def preview(self, due, article):
        if due:
            post, day = due[0]
            try:
                text, facets = scheduled_post_facets(post.text)
                problem = None
            except BlueskyError as exc:
                text, facets, problem = post.text, [], str(exc)
            features = [facet["features"][0] for facet in facets]
            self.stdout.write(json.dumps({
                "scheduled_post": post.name, "date": day.isoformat(),
                "post_time": post.post_time.isoformat(timespec="minutes"), "text": text,
                "links": [feature["uri"] for feature in features if "uri" in feature],
                "hashtags": [feature["tag"] for feature in features if "tag" in feature],
                "error": problem,
                "also_due": [other.name for other, _ in due[1:]],
                "article_waiting": article is not None,
            }, ensure_ascii=False, indent=2))
            return
        try:
            text, _ = post_text(article)
        except BlueskyError as exc:
            raise CommandError(f"Article {article.pk}: {exc}") from exc
        self.stdout.write(json.dumps({
            "article_id": article.pk, "text": text, "link": article.url,
            "title": article.title, "image": article.image_url or "Local placeholder",
            "image_fallback": "Stable local placeholder if the image is absent or unusable.",
            "mention": "Resolved to a clickable mention during live posting." if article.site.bluesky else None,
        }, ensure_ascii=False, indent=2))

    def post_scheduled(self, client, post, day):
        """Return True when this occurrence is posted (or was already posted)."""
        # Commit the reservation before external side effects. Retries reuse the key.
        with transaction.atomic():
            run, _ = ScheduledPostRun.objects.select_for_update().get_or_create(
                scheduled_post=post, date=day,
                defaults={"text": post.text.strip(), "bluesky_rkey": new_record_key()},
            )
        if run.posted_at:
            self.stdout.write(f"Scheduled post '{post.name}' was posted by another run.")
            return True
        with transaction.atomic():
            locked = ScheduledPostRun.objects.select_for_update().get(pk=run.pk)
            if locked.posted_at:
                self.stdout.write(f"Scheduled post '{post.name}' was posted by another run.")
                return True
            current = ScheduledPost.objects.filter(pk=post.pk, active=True).first()
            if current is None or not current.runs_on(day):
                self.stdout.write(f"Scheduled post '{post.name}' is no longer due; nothing posted.")
                return False
            # If an earlier attempt never reached Bluesky, post the latest edited text.
            if locked.text != current.text.strip() and client.existing_scheduled_post(locked) is None:
                locked.text = current.text.strip()
                locked.save(update_fields=["text"])
            uri = client.publish_scheduled(locked)
            locked.uri = uri
            locked.posted_at = timezone.now()
            locked.error = ""
            locked.save(update_fields=["uri", "posted_at", "error"])
        self.stdout.write(self.style.SUCCESS(f"Scheduled post '{post.name}' posted/reconciled: {uri}"))
        return True

    def post_article(self, client, article):
        text, _ = post_text(article)
        # Commit the key before external side effects. Never allocate a new key on retry.
        with transaction.atomic():
            reserved = Articles.objects.select_for_update().get(pk=article.pk)
            if reserved.bluesky:
                self.stdout.write("This article was posted by another run; nothing posted.")
                return
            if not reserved.bluesky_rkey:
                reserved.bluesky_rkey = new_record_key()
                reserved.save(update_fields=["bluesky_rkey"])

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
        self.stdout.write(self.style.SUCCESS(f"Article {article.pk} posted/reconciled: {uri}"))
