import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from website import views
from website.models import Adverts, Articles, Clicks, Logic, Sites


class ClickTrackingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        cls.article_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        cls.site = Sites.objects.create(
            name="Site", url="https://s.example.com", rss_feed="https://s.example.com/feed",
            category=cat, description="x",
        )
        cls.article = Articles.objects.create(
            title="A", url="https://s.example.com/a", image_url="", site=cls.site,
            published=timezone.localdate(),
        )
        cls.other = Articles.objects.create(
            title="B", url="https://s.example.com/b", image_url="", site=cls.site,
            published=timezone.localdate(),
        )

    def go(self, article):
        return self.client.get(f"/go/{article.pk}/")

    def test_click_redirects_counts_and_records(self):
        response = self.go(self.article)
        self.assertRedirects(response, self.article.url, fetch_redirect_response=False)
        self.article.refresh_from_db()
        self.assertEqual(self.article.clicks, 1)
        click = Clicks.objects.get()
        self.assertEqual(click.type, self.article_type)
        self.assertEqual(click.article, str(self.article.pk))
        self.assertEqual(click.site, self.site)

    def test_repeat_click_within_24_hours_still_redirects_but_is_not_counted(self):
        self.go(self.article)
        response = self.go(self.article)
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.clicks, 1)
        self.assertEqual(Clicks.objects.count(), 1)

    def test_different_articles_are_counted_separately(self):
        self.go(self.article)
        self.go(self.other)
        self.assertEqual(Clicks.objects.count(), 2)

    def test_counts_again_after_24_hours(self):
        self.go(self.article)
        later = time.time() + views.CLICK_WINDOW_SECONDS + 5
        with mock.patch("website.views.time.time", return_value=later):
            self.go(self.article)
        self.article.refresh_from_db()
        self.assertEqual(self.article.clicks, 2)

    def test_tampered_or_junk_cookie_is_ignored(self):
        self.client.cookies[views.CLICK_COOKIE] = "not-a-valid-signature"
        self.go(self.article)
        self.assertEqual(Clicks.objects.count(), 1)

    def test_a_new_browser_is_counted(self):
        self.go(self.article)
        self.client.cookies.clear()
        self.go(self.article)
        self.assertEqual(Clicks.objects.count(), 2)

    def test_hidden_or_missing_articles_are_404(self):
        Articles.objects.filter(pk=self.other.pk).update(hidden=True)
        self.assertEqual(self.go(self.other).status_code, 404)
        self.assertEqual(self.client.get("/go/999999/").status_code, 404)

    def test_cards_link_through_the_tracker_and_crawlers_are_kept_out(self):
        self.assertContains(self.client.get("/newest/"), f'href="/go/{self.article.pk}/"')
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /go/")

    def test_rank_goes_up_with_a_click(self):
        before = Articles.objects.get(pk=self.article.pk).rank
        self.go(self.article)
        self.assertEqual(Articles.objects.get(pk=self.article.pk).rank, before + 1)


class AdvertClickTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.advert_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Advert")
        cls.article_type = Logic.objects.create(logic_type="CLICK_TYPE", value="Article")
        size = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")
        cat = Logic.objects.create(logic_type="CATEGORY", value="Video Games")
        site = Sites.objects.create(
            name="Site", url="https://s.example.com", rss_feed="https://s.example.com/feed",
            category=cat, description="x",
        )
        cls.article = Articles.objects.create(
            title="A", url="https://s.example.com/a", image_url="", site=site, published=timezone.localdate(),
        )
        today = timezone.localdate()
        make = lambda start, end: Adverts.objects.create(
            title="Ad", message="Try this", site_name="Blog", site_url="https://b.example.com",
            start_date=start, end_date=end, concurrency=1, advert_size=size,
        )
        cls.advert = make(today - timedelta(days=1), today + timedelta(days=1))
        cls.expired = make(today - timedelta(days=9), today - timedelta(days=2))

    def test_click_redirects_counts_and_records_an_advert_click(self):
        response = self.client.get(f"/go/ad/{self.advert.pk}/")
        self.assertRedirects(response, "https://b.example.com", fetch_redirect_response=False)
        self.advert.refresh_from_db()
        self.assertEqual(self.advert.clicks, 1)
        click = Clicks.objects.get()
        self.assertEqual(click.type, self.advert_type)
        self.assertEqual(click.article, str(self.advert.pk))

    def test_repeat_click_within_24_hours_is_not_counted(self):
        self.client.get(f"/go/ad/{self.advert.pk}/")
        response = self.client.get(f"/go/ad/{self.advert.pk}/")
        self.assertEqual(response.status_code, 302)
        self.advert.refresh_from_db()
        self.assertEqual(self.advert.clicks, 1)
        self.assertEqual(Clicks.objects.count(), 1)

    def test_counts_again_after_24_hours(self):
        self.client.get(f"/go/ad/{self.advert.pk}/")
        later = time.time() + views.CLICK_WINDOW_SECONDS + 5
        with mock.patch("website.views.time.time", return_value=later):
            self.client.get(f"/go/ad/{self.advert.pk}/")
        self.advert.refresh_from_db()
        self.assertEqual(self.advert.clicks, 2)

    def test_an_article_and_advert_with_the_same_id_do_not_block_each_other(self):
        self.client.get(f"/go/{self.article.pk}/")
        self.client.get(f"/go/ad/{self.advert.pk}/")
        self.assertEqual(Clicks.objects.count(), 2)
        self.assertEqual(Clicks.objects.filter(type=self.advert_type).count(), 1)

    def test_expired_advert_redirects_without_counting(self):
        response = self.client.get(f"/go/ad/{self.expired.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Clicks.objects.count(), 0)

    def test_unknown_advert_is_404(self):
        self.assertEqual(self.client.get("/go/ad/999999/").status_code, 404)

    def test_advert_card_links_through_the_tracker(self):
        self.assertContains(self.client.get("/newest/"), f'href="/go/ad/{self.advert.pk}/"')
