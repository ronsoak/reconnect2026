"""
Fills in the image for articles that don't have one, using the page's preview image.

Articles whose page has no image or can't be fetched are left blank (they show the
placeholder block on the site). Only articles with a blank image are touched, and
nothing is ever deleted or overwritten.

Examples:
    python manage.py backfill_images                 # every blank article, newest first
    python manage.py backfill_images --limit 50      # just the 50 newest blank ones
    python manage.py backfill_images --dry-run       # show what would be saved, change nothing
    python manage.py backfill_images --workers 4     # fewer parallel downloads
"""
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand

from website.models import Articles


def fetch_image(url):
    """Preview image for a page, or "" if there isn't one or the page can't be read."""
    from linkpreview import link_preview

    try:
        return (link_preview(url, parser="lxml").image or "")[:512]
    except Exception:
        return ""


class Command(BaseCommand):
    help = "Fetch preview images for articles that have a blank image."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Maximum articles to try (0 = all).")
        parser.add_argument("--workers", type=int, default=8, help="Parallel downloads (default 8).")
        parser.add_argument("--dry-run", action="store_true", help="Report only, save nothing.")

    def handle(self, *args, **options):
        articles = Articles.objects.filter(image_url="").order_by("-published", "pk")
        if options["limit"] > 0:
            articles = articles[: options["limit"]]
        articles = list(articles.only("pk", "url"))
        self.stdout.write(f"Trying {len(articles)} articles without an image")

        with ThreadPoolExecutor(max_workers=max(1, options["workers"])) as pool:
            images = list(pool.map(lambda article: fetch_image(article.url), articles))

        found = 0
        for article, image in zip(articles, images):
            if not image:
                continue
            found += 1
            if not options["dry_run"]:
                # Only fill blanks, in case the article gained an image while this ran
                Articles.objects.filter(pk=article.pk, image_url="").update(image_url=image)

        verb = "Would save" if options["dry_run"] else "Saved"
        self.stdout.write(self.style.SUCCESS(f"{verb} {found} images; {len(articles) - found} left blank"))
