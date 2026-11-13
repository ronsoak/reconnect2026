from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from website.analytics_reports import AnalyticsReportForm, build_report, render_report_markdown
from website.models import Adverts, Analytics, Articles, Clicks, Logging, Logic, Sites


TODAY = date(2026, 11, 13)


class AnalyticsReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.rss_type = Logic.objects.create(logic_type="CLICK_TYPE", value="RSS")
        cls.advert_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Advert")
        size = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        cls.site = Sites.objects.create(
            name="Hidden publication", url="https://site.example.com",
            rss_feed="https://site.example.com/feed", description="Test", hidden=True, recap=False,
        )
        cls.other_site = Sites.objects.create(
            name="Other publication", url="https://other.example.com",
            rss_feed="https://other.example.com/feed", description="Test",
        )
        cls.article = Articles.objects.create(
            title="An old hidden article", url="https://site.example.com/old", image_url="",
            published=date(2020, 1, 1), site=cls.site, hidden=True, site_hide=True,
        )
        cls.advert = Adverts.objects.create(
            title="Client A", message="Advert A", site_url="https://a.example.com",
            advert_size=size, start_date=date(2026, 1, 1), end_date=date(2026, 2, 1),
        )
        cls.other_advert = Adverts.objects.create(
            title="Client B", message="Advert B", site_url="https://b.example.com",
            advert_size=size, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        )
        cls.admin = get_user_model().objects.create_superuser("boss", "boss@example.com", "pw")

    def report(self, kind="sites", start=date(2026, 9, 1), end=None, **kwargs):
        return build_report(kind, start, end or start, today=TODAY, **kwargs)

    def summary(self, month, clicks, *, kind=None, object_id=None, site=None, baseline=False):
        return Analytics.objects.create(
            type=kind or self.article_type,
            object_id=self.article.pk if object_id is None else object_id,
            site=site, month=month, clicks=clicks, is_baseline=baseline,
        )

    def complete(self, month):
        Logging.objects.create(
            log_type="ANALYTICS_TASK", value=f"{month:%Y-%m}: 2 rows from 8 clicks",
        )

    def test_publications_combine_rss_and_article_clicks_without_editorial_filters(self):
        self.summary(date(2026, 9, 1), 5, site=self.site)
        self.summary(date(2026, 9, 1), 3, kind=self.rss_type, site=self.site)
        self.summary(date(2026, 9, 1), 90, kind=self.advert_type, object_id=self.advert.pk)
        self.complete(date(2026, 9, 1))
        data = self.report()
        self.assertEqual(data["total"], 8)
        row = next(row for row in data["rows"] if row["id"] == self.site.pk)
        self.assertEqual(row["cells"], [{"clicks": 8}])
        self.assertEqual(data["top_articles"][0]["title"], self.article.title)
        self.assertEqual(data["top_articles"][0]["clicks"], 8)
        self.assertIn(self.site.name, render_report_markdown(data))

    def test_baselines_are_separate_and_never_part_of_activity(self):
        self.summary(date(2026, 10, 1), 500, site=self.site, baseline=True)
        self.summary(date(2026, 9, 1), 5, site=self.site)
        self.complete(date(2026, 9, 1))
        data = self.report(end=date(2026, 10, 1), include_baseline=True)
        self.assertEqual(data["total"], 5)
        self.assertIsNone(data["columns"][1]["clicks"])
        self.assertEqual(data["top_articles"][0]["clicks"], 5)
        self.assertEqual(data["baseline_rows"][0]["clicks"], 500)
        self.assertIn("Imported historical totals (not monthly activity)", render_report_markdown(data))
        self.assertEqual(self.report(start=date(2026, 10, 1))["baseline_rows"], [])

    def test_missing_month_is_not_zero_but_completed_zero_is(self):
        self.complete(date(2026, 9, 1))
        data = self.report(end=date(2026, 10, 1))
        self.assertEqual(data["columns"][0]["clicks"], 0)
        self.assertIsNone(data["columns"][1]["clicks"])
        self.assertEqual(data["columns"][1]["status"], "Not aggregated")
        self.assertIn("| Oct 2026 | N/A | Not aggregated |", render_report_markdown(data))

    def test_saved_rows_without_completion_log_are_labelled_unverified(self):
        self.summary(date(2026, 9, 1), 5, site=self.site)
        data = self.report()
        self.assertEqual(data["total"], 5)
        self.assertIn("unverified", data["columns"][0]["status"])
        missing = next(row for row in data["rows"] if row["id"] == self.other_site.pk)
        self.assertIsNone(missing["cells"][0]["clicks"])

    def test_current_month_uses_raw_clicks_only_not_saved_summary(self):
        self.summary(date(2026, 11, 1), 40, site=self.site)
        for kind in (self.article_type, self.rss_type):
            Clicks.objects.create(
                type=kind, article=str(self.article.pk), site=self.site, date=TODAY,
            )
        Clicks.objects.create(
            type=self.article_type, article=str(self.article.pk), site=self.site,
            date=date(2026, 11, 30),
        )
        data = self.report(start=date(2026, 11, 1))
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["top_articles"][0]["clicks"], 2)
        self.assertIn("Provisional", data["columns"][0]["status"])

    def test_client_filter_excludes_other_adverts_and_resolves_expired_advert(self):
        self.summary(date(2026, 9, 1), 7, kind=self.advert_type, object_id=self.advert.pk)
        self.summary(date(2026, 9, 1), 25, kind=self.advert_type, object_id=self.other_advert.pk)
        self.summary(date(2026, 10, 1), 99, kind=self.advert_type,
                     object_id=self.other_advert.pk, baseline=True)
        data = self.report(
            kind="adverts", end=date(2026, 10, 1),
            object_id=str(self.advert.pk), include_baseline=True,
        )
        text = render_report_markdown(data)
        self.assertEqual(data["total"], 7)
        self.assertEqual(len(data["rows"]), 1)
        self.assertIn("Client A", text)
        self.assertIn("01 Jan 2026 to 01 Feb 2026", text)
        self.assertNotIn("Client B", text)
        self.assertEqual(data["baseline_rows"], [])

    def test_deleted_objects_remain_visible_with_readable_fallbacks(self):
        self.summary(date(2026, 9, 1), 4, site=self.site, object_id=999)
        self.assertEqual(self.report()["top_articles"][0]["title"], "Deleted article #999")
        self.summary(date(2026, 9, 1), 6, kind=self.advert_type, object_id=999)
        adverts = self.report(kind="adverts")
        self.assertTrue(any("advert #999" in row["name"] for row in adverts["rows"]))
        self.assertEqual(adverts["total"], 6)

    def test_publication_filter_applies_to_articles_baselines_and_raw_clicks(self):
        self.summary(date(2026, 9, 1), 3, site=self.site)
        self.summary(date(2026, 9, 1), 99, object_id=999, site=self.other_site)
        Clicks.objects.create(
            type=self.article_type, article="999", site=self.other_site, date=TODAY,
        )
        data = self.report(end=date(2026, 11, 1), object_id=str(self.site.pk))
        self.assertEqual(data["total"], 3)
        self.assertEqual([row["id"] for row in data["rows"]], [self.site.pk])
        self.assertNotIn(self.other_site.name, render_report_markdown(data))

    def test_month_year_and_rolling_forms_validate_periods(self):
        with mock.patch("website.analytics_reports.timezone.localdate", return_value=TODAY):
            for period, start, end in (
                ("month", date(2026, 1, 1), date(2026, 1, 1)),
                ("year", date(2025, 1, 1), date(2025, 12, 1)),
                ("rolling", date(2025, 2, 1), date(2026, 1, 1)),
            ):
                form = AnalyticsReportForm({
                    "report": "adverts", "period": period, "month": "2026-01", "year": "2025",
                })
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual((form.cleaned_data["start"], form.cleaned_data["end"]), (start, end))
        form = AnalyticsReportForm({"report": "adverts", "period": "month", "month": "bad"})
        self.assertFalse(form.is_valid())

    def test_admin_permissions_apply_to_preview_and_download(self):
        url = "/backdoor/analytics-reports/"
        self.assertEqual(self.client.get(url).status_code, 302)
        staff = get_user_model().objects.create_user("staff", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.get(url + "?download=1").status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_analytics"))
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_preview_and_download_share_filters_and_totals(self):
        self.client.force_login(self.admin)
        self.summary(date(2026, 9, 1), 7, kind=self.advert_type, object_id=self.advert.pk)
        self.summary(date(2026, 9, 1), 99, kind=self.advert_type, object_id=self.other_advert.pk)
        params = {
            "report": "adverts", "period": "month", "month": "2026-09",
            "object_id": self.advert.pk,
        }
        with mock.patch("website.admin_views.timezone.localdate", return_value=TODAY):
            page = self.client.get("/backdoor/analytics-reports/", params)
            self.assertContains(page, "7 recorded clicks")
            data = page.context["report"]
            download = self.client.get("/backdoor/analytics-reports/", {**params, "download": "1"})
        self.assertEqual(download.content.decode(), render_report_markdown(data))
        self.assertNotIn("Client B", download.content.decode())
        self.assertIn(f"adverts-{self.advert.pk}-2026-09", download["Content-Disposition"])

    def test_invalid_export_returns_form_errors_not_a_report(self):
        self.client.force_login(self.admin)
        for params in (
            {"period": "bad"}, {"month": "2026-13"}, {"object_id": "999999"},
            {"report": "unknown"}, {"period": "year", "year": "no"},
        ):
            with self.subTest(params=params):
                response = self.client.get(
                    "/backdoor/analytics-reports/", {**params, "download": "1"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Please correct", status_code=400)
                self.assertNotIn("Content-Disposition", response)

    def test_markdown_escapes_titles_and_unsafe_links(self):
        self.site.name = "Name | [fake]\n<script>"
        self.site.url = "javascript:alert(1)"
        self.site.save()
        data = self.report(object_id=str(self.site.pk))
        text = render_report_markdown(data)
        self.assertIn(r"Name \| \[fake\]", text)
        self.assertNotIn("<script>", text)
        self.assertNotIn("javascript:", text)

    def test_download_is_not_limited_to_preview_page(self):
        for index in range(52):
            Sites.objects.create(
                name=f"Extra {index}", url=f"https://extra{index}.example.com",
                rss_feed=f"https://extra{index}.example.com/feed", description="Test",
            )
        self.client.force_login(self.admin)
        params = {"report": "sites", "month": "2026-09"}
        page = self.client.get("/backdoor/analytics-reports/", params)
        self.assertEqual(len(page.context["page"]), 50)
        download = self.client.get("/backdoor/analytics-reports/", {**params, "download": "1"})
        self.assertEqual(len(page.context["report"]["rows"]), 54)
        self.assertIn("Extra 51", download.content.decode())
        self.assertContains(self.client.get("/backdoor/"), "/backdoor/analytics-reports/")

    def test_article_report_combines_monthly_clicks_and_resolves_publications(self):
        self.summary(date(2026, 9, 1), 5, site=self.site)
        self.summary(date(2026, 9, 1), 3, kind=self.rss_type, site=self.site)
        self.summary(date(2026, 9, 1), 90, kind=self.advert_type, object_id=self.advert.pk)
        self.summary(date(2026, 10, 1), 500, site=self.site, baseline=True)
        self.complete(date(2026, 9, 1))
        data = self.report(kind="articles", end=date(2026, 10, 1), include_baseline=True)
        self.assertEqual(data["heading"], "Article analytics")
        self.assertEqual(data["total"], 8)
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual((row["name"], row["publication"], row["url"]),
                         (self.article.title, self.site.name, self.article.url))
        self.assertEqual(row["cells"], [{"clicks": 8}, {"clicks": None}])
        self.assertEqual(data["baseline_rows"][0]["clicks"], 500)
        self.assertEqual(data["top_articles"], [])
        self.assertIn("| Name | Publication | Sep 2026 |", render_report_markdown(data))

    def test_article_report_filters_saved_raw_and_baseline_by_publication(self):
        self.summary(date(2026, 9, 1), 3, site=self.site)
        self.summary(date(2026, 9, 1), 99, object_id=999, site=self.other_site)
        self.summary(date(2026, 10, 1), 500, object_id=999, site=self.other_site, baseline=True)
        for kind in (self.article_type, self.rss_type):
            Clicks.objects.create(type=kind, article=str(self.article.pk), site=self.site, date=TODAY)
        Clicks.objects.create(type=self.article_type, article="999", site=self.other_site, date=TODAY)
        data = self.report(
            kind="articles", end=date(2026, 11, 1),
            object_id=str(self.site.pk), include_baseline=True,
        )
        self.assertEqual(data["total"], 5)
        self.assertEqual([row["id"] for row in data["rows"]], [self.article.pk])
        self.assertEqual(data["rows"][0]["cells"][-1]["clicks"], 2)
        self.assertEqual(data["baseline_rows"], [])
        self.assertEqual(data["selection"], self.site.name)
        self.assertNotIn(self.other_site.name, render_report_markdown(data))

    def test_article_report_retains_deleted_article_and_its_stored_publication(self):
        self.summary(date(2026, 9, 1), 4, site=self.site, object_id=999)
        data = self.report(kind="articles")
        self.assertEqual(data["rows"][0]["name"], "Deleted / unknown article #999")
        self.assertEqual(data["rows"][0]["publication"], self.site.name)
        self.assertEqual(data["total"], 4)

    def test_articles_tab_exports_all_articles_not_only_top_twenty_or_first_page(self):
        for index in range(53):
            article = Articles.objects.create(
                title=f"Monthly article {index:02}", url=f"https://site.example.com/{index}",
                image_url="", site=self.site,
            )
            self.summary(date(2026, 9, 1), index + 1, object_id=article.pk, site=self.site)
        self.client.force_login(self.admin)
        params = {
            "report": "articles", "period": "month", "month": "2026-09",
            "object_id": self.site.pk,
        }
        page = self.client.get("/backdoor/analytics-reports/", params)
        self.assertContains(page, "Article analytics")
        self.assertContains(page, "Publication")
        self.assertEqual(len(page.context["page"]), 50)
        self.assertEqual(len(page.context["report"]["rows"]), 53)
        self.assertEqual(page.context["report"]["rows"][0]["name"], "Monthly article 52")
        download = self.client.get("/backdoor/analytics-reports/", {**params, "download": "1"})
        self.assertEqual(download.content.decode(), render_report_markdown(page.context["report"]))
        self.assertIn("Monthly article 00", download.content.decode())
        self.assertIn("Monthly article 52", download.content.decode())
        self.assertIn("analytics-articles-", download["Content-Disposition"])

    def test_article_form_uses_publication_choices_not_an_article_dropdown(self):
        form = AnalyticsReportForm({
            "report": "articles", "period": "month", "month": "2026-09",
            "object_id": str(self.site.pk),
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fields["object_id"].label, "Publication")
        self.assertEqual(form.fields["object_id"].choices[0], ("", "All publications"))
