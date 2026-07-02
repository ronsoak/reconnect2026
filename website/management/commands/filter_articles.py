# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Fitler Articles
#
# Hides articels based on the keywords in my Logic Model.
#
# Command Examples
#   Run (hide matches, default): python manage.py filter_articles
#   Run dry-run to see how many would change (no DB writes): python manage.py filter_articles --dry-run
#   Unhide matching articles instead of hiding: python manage.py filter_articles --unhide
#   Restrict to a specific site (site primary key 5): python manage.py filter_articles --site 5
#   Apply only a specific keyword (useful for testing): python manage.py filter_articles --keyword "spoiler"
# ===== ===== ===== ===== ===== ===== ===== ===== ===== ===== 
# Imports
# ===== ===== ===== ===== 
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from typing import Any, Optional, Iterable, List
from website.models import Articles, Logic, Logging, Sites

# ===== ===== ===== ===== 
# Command
# ===== ===== ===== ===== 
class Command(BaseCommand):
    help = (
        "Hides articels based on the keywords in my Logic Model."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--unhide",
            action="store_true",
            help="Unhide matching articles instead of hiding them (sets hidden=False).",
        )
        parser.add_argument(
            "--site",
            type=int,
            help="Optional site PK to restrict filtering to a single site.",
        )
        parser.add_argument(
            "--keyword",
            type=str,
            help="Optional single keyword to apply (useful for testing). If omitted, all KEYWORD logic values are used.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many articles would be changed but do not perform updates.",
        )

    def handle(self, *args: Any, **options: Any):
        unhide: bool = options.get("unhide", False)
        site_pk: Optional[int] = options.get("site")
        single_keyword: Optional[str] = options.get("keyword")
        dry_run: bool = options.get("dry_run", False)

        # Collect keywords
        if single_keyword:
            keywords = [single_keyword]
        else:
            keywords = list(
                Logic.objects.filter(logic_type="KEYWORD").values_list("value", flat=True)
            )

        if not keywords:
            self.stdout.write("No keywords found (and no --keyword provided). Nothing to do.")
            return

        # Build combined Q for title matches
        title_q = Q()
        for kw in keywords:
            # skip empty keywords just in case
            if not kw:
                continue
            title_q |= Q(title__icontains=kw)

        qs = Articles.objects.filter(title_q)  # type: ignore[arg-type]

        # If site restriction requested
        if site_pk is not None:
            qs = qs.filter(site_id=site_pk)

        desired_flag = False if unhide else True
        to_change_qs = qs.exclude(hidden=desired_flag)

        count_to_change = to_change_qs.count()
        self.stdout.write(
            f"Keywords: {len(keywords)}. Articles matching title filter: {qs.count()}. "
            f"Articles to change (hidden -> {desired_flag}): {count_to_change}"
        )

        if count_to_change == 0:
            self.stdout.write("No articles need changing. No Logging entry written.")
            return

        if dry_run:
            self.stdout.write("Dry-run enabled; no changes performed.")
            return

        # Perform update in a transaction
        try:
            with transaction.atomic():
                updated = to_change_qs.update(hidden=desired_flag)
        except Exception as e:
            self.stderr.write(f"Failed to update articles: {e}")
            return 1

        self.stdout.write(f"Updated {updated} article(s) (set hidden={desired_flag}).")

        # Write Logging record only if at least one article changed
        try:
            if updated > 0:
                Logging.objects.create(
                    log_type="FILTER_ARTICLE_TASK",
                    value=f"Filtered: [{updated}] articles filtered.",
                )
        except Exception as e:
            # Don't raise — log the failure to stderr
            self.stderr.write(f"Failed to write Logging record: {e}")

        return 0