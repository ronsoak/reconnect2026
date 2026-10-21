from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase, override_settings

from website.models import Articles, Clicks, Logic, Sites
from website.newsletter import (
    build_newsletter, month_range_for, period_range, render_markdown, week_start_for,
)

# Monday 5 Oct 2026 to Sunday 11 Oct 2026
MONDAY = date(2026, 10, 5)


class WeekTests(TestCase):
    def test_week_starts_on_monday_for_any_day(self):
        for day in range(5, 12):
            self.assertEqual(week_start_for("this", date(2026, 10, day)), MONDAY)

    def test_last_week_is_seven_days_earlier(self):
        self.assertEqual(week_start_for("last", date(2026, 10, 11)), date(2026, 9, 28))


class MonthTests(TestCase):
    def test_this_and_last_month(self):
        today = date(2026, 10, 13)
        self.assertEqual(month_range_for("this", today), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(month_range_for("last", today), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_last_month_crosses_the_year_and_leap_february(self):
        self.assertEqual(month_range_for("last", date(2026, 1, 5)), (date(2025, 12, 1), date(2025, 12, 31)))
        self.assertEqual(month_range_for("this", date(2028, 2, 10)), (date(2028, 2, 1), date(2028, 2, 29)))

    def test_period_range_top_counts(self):
        self.assertEqual(period_range("week", "this", date(2026, 10, 7))[2], settings.NEWSLETTER_WEEKLY_TOP_COUNT)
        self.assertEqual(period_range("month", "this", date(2026, 10, 7))[2], settings.NEWSLETTER_MONTHLY_TOP_COUNT)


class NewsletterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.tag = Logic.objects.create(logic_type="TAG", value="News")
        cls.click_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.site = cls.make_site("Blog")

    @classmethod
    def make_site(cls, name, **extra):
        slug = name.lower().replace(" ", "-")
        site = Sites.objects.create(
            name=name, url=f"https://{slug}.example.com", rss_feed=f"https://{slug}.example.com/feed",
            category=cls.category, description="Test site", **extra,
        )
        site.tags.set([cls.tag])
        return site

    def article(self, title, day=7, site=None, clicks=0, **extra):
        article = Articles.objects.create(
            title=title, url=f"https://x.example.com/{title.replace(' ', '-')}", image_url="",
            site=site or self.site, published=MONDAY + timedelta(days=day - 5), **extra,
        )
        for _ in range(clicks):
            Clicks.objects.create(type=self.click_type, article=str(article.pk), date=MONDAY + timedelta(days=2))
        return article

    def build(self):
        return build_newsletter(MONDAY)

    def titles(self, rows):
        return [a.title for a in rows]

    def test_only_the_selected_week_is_included(self):
        self.article("Monday", day=5)
        self.article("Sunday", day=11)
        self.article("Before", day=4)
        self.article("After", day=12)
        data = self.build()
        self.assertEqual(sorted(self.titles(data["remaining"])), ["Monday", "Sunday"])

    def test_hidden_and_recap_off_are_left_out(self):
        self.article("Hidden", hidden=True)
        self.article("Site hidden", site_hide=True)
        self.article("Premium", site=self.make_site("Premium", recap=False))
        self.article("Hidden site", site=self.make_site("Gone", hidden=True))
        self.article("Kept")
        self.assertEqual(self.titles(self.build()["remaining"]), ["Kept"])

    def test_excluded_terms_match_whole_words_only(self):
        Logic.objects.create(logic_type="NEWSLETTER_EXCLUDED_TERM", value="review")
        self.article("A Review of Zelda")
        self.article("Zelda review")
        self.article("Preview of Zelda")
        self.assertEqual(self.titles(self.build()["remaining"]), ["Preview of Zelda"])

    def test_top_section_ranks_by_weekly_clicks_and_skips_zero_clicks(self):
        self.article("Two", clicks=2)
        self.article("Five", clicks=5)
        self.article("None")
        data = self.build()
        self.assertEqual(self.titles(data["top"]), ["Five", "Two"])
        self.assertEqual(self.titles(data["remaining"]), ["None"])

    def test_clicks_outside_the_week_do_not_count(self):
        article = self.article("Old clicks")
        Clicks.objects.create(type=self.click_type, article=str(article.pk), date=MONDAY - timedelta(days=1))
        self.assertEqual(self.build()["top"], [])

    def test_top_section_is_capped(self):
        for i in range(settings.NEWSLETTER_WEEKLY_TOP_COUNT + 2):
            self.article(f"Article {i}", clicks=1)
        data = self.build()
        self.assertEqual(len(data["top"]), settings.NEWSLETTER_WEEKLY_TOP_COUNT)
        self.assertEqual(len(data["remaining"]), 2)

    def test_markdown_has_both_sections_and_details(self):
        self.article("Hot", clicks=3)
        self.article("Quiet")
        text = render_markdown(self.build())
        self.assertIn("## Top 30 by clicks this week", text)
        self.assertIn("1. [Hot](https://x.example.com/Hot)", text)
        self.assertIn("Blog | Video Games | News | 3 clicks", text)
        self.assertIn("- [Quiet](https://x.example.com/Quiet)", text)


class NewsletterAdminPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("boss", "b@example.com", "pw")

    def test_requires_admin_login(self):
        response = self.client.get("/backdoor/newsletter/")
        self.assertEqual(response.status_code, 302)

    def test_page_and_download_work(self):
        self.client.force_login(self.admin)
        page = self.client.get("/backdoor/newsletter/?period=month&which=last")
        self.assertContains(page, "Download markdown")
        download = self.client.get("/backdoor/newsletter/?download=1")
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertIn(".md", download["Content-Disposition"])
        self.assertIn("# Reconnect Recap", download.content.decode())

    def test_monthly_download_uses_month_in_name_and_top_60(self):
        self.client.force_login(self.admin)
        download = self.client.get("/backdoor/newsletter/?period=month&download=1")
        self.assertIn("recap-month-", download["Content-Disposition"])
        self.assertIn("## Top 60 by clicks this month", download.content.decode())

    def test_admin_front_page_links_to_the_export(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/backdoor/"), "/backdoor/newsletter/")

    @override_settings(NEWSLETTER_WEEKLY_TOP_COUNT=4, NEWSLETTER_MONTHLY_TOP_COUNT=4)
    def test_equal_configured_counts_keep_preview_and_download_periods(self):
        self.client.force_login(self.admin)
        for period in ("week", "month"):
            with self.subTest(period=period):
                preview = self.client.get(f"/backdoor/newsletter/?period={period}")
                self.assertEqual(preview.context["top_count"], 4)
                self.assertEqual(preview.context["period"], period)
                download = self.client.get(f"/backdoor/newsletter/?period={period}&download=1")
                self.assertIn(f"## Top 4 by clicks this {period}", download.content.decode())
