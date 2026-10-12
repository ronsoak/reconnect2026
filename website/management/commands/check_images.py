# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Check Images
#
# Finds article image addresses that can't work and blanks them, so the card is shown as a
# text card instead of a broken image. Only image_url is changed, articles are never deleted.
#
# Two levels:
#   Format check (default, fast, no network): blanks anything that isn't a full http(s) address,
#     for example '/static/og-image.png'.
#   --remote: also fetches each address and blanks it if the server doesn't answer with an image.
#     Fetches go through website/safe_fetch.py, so internal addresses are refused.
#
# Blanked articles are picked up again by backfill_images if you want to retry them.
#
# Command Examples
#   See what the format check would blank:        python manage.py check_images --dry-run
#   Blank bad addresses:                          python manage.py check_images
#   Also test every address over the network:     python manage.py check_images --remote
#   Test only the 200 newest, fewer downloads:    python manage.py check_images --remote --limit 200 --workers 4
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== =====
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand

from website.images import is_valid_image_url
from website.models import Articles
from website.safe_fetch import UnsafeURL, build_safe_session

session = build_safe_session(retries=0, user_agent="django-ingest-bot/1.0")


# ===== ===== ===== =====
# Helpers
# ===== ===== ===== =====
def remote_image_works(url, timeout=10):
    """True if the address answers with an image. Reads the headers only, not the whole file."""
    try:
        response = session.get(url, timeout=timeout, stream=True, allow_redirects=True)
        with response:
            content_type = response.headers.get("Content-Type", "").lower()
            return response.ok and content_type.startswith("image/")
    except (UnsafeURL, Exception):
        return False


# ===== ===== ===== =====
# Command
# ===== ===== ===== =====
class Command(BaseCommand):
    help = "Blank article image addresses that are invalid, so the card becomes a text card."

    def add_arguments(self, parser):
        parser.add_argument("--remote", action="store_true", help="Also fetch each address and check it is an image.")
        parser.add_argument("--limit", type=int, default=0, help="Only check the newest N articles with an image (0 = all).")
        parser.add_argument("--workers", type=int, default=8, help="Parallel downloads for --remote (default 8).")
        parser.add_argument("--dry-run", action="store_true", help="Report only, change nothing.")

    def handle(self, *args, **options):
        articles = Articles.objects.exclude(image_url="").order_by("-published", "pk")
        if options["limit"] > 0:
            articles = articles[: options["limit"]]
        articles = list(articles.only("pk", "image_url"))
        self.stdout.write(f"Checking {len(articles)} articles with an image")

        bad = [a for a in articles if not is_valid_image_url(a.image_url)]
        format_bad = len(bad)

        if options["remote"]:
            good = [a for a in articles if is_valid_image_url(a.image_url)]
            with ThreadPoolExecutor(max_workers=max(1, options["workers"])) as pool:
                results = list(pool.map(lambda a: remote_image_works(a.image_url), good))
            bad += [a for a, ok in zip(good, results) if not ok]

        for article in bad[:10]:
            self.stdout.write(f"  bad: {article.image_url}")

        if not options["dry_run"] and bad:
            Articles.objects.filter(pk__in=[a.pk for a in bad]).update(image_url="")

        verb = "Would blank" if options["dry_run"] else "Blanked"
        self.stdout.write(self.style.SUCCESS(f"{verb} {len(bad)} ({format_bad} bad format, {len(bad) - format_bad} not an image)"))
