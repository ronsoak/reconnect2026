from django.contrib.auth import get_user_model
from django.test import TestCase

from website.models import FrontPageNotice


class FrontPageNoticeTests(TestCase):
    def test_active_notice_is_shown_only_on_dynamic_home_page(self):
        FrontPageNotice.objects.create(message="Scheduled maintenance tonight.", is_active=True)

        self.assertContains(self.client.get("/"), "Scheduled maintenance tonight.")
        self.assertNotContains(self.client.get("/newest/"), "Scheduled maintenance tonight.")
        self.assertNotContains(self.client.get("/about/"), "Scheduled maintenance tonight.")

    def test_inactive_notice_is_not_shown(self):
        FrontPageNotice.objects.create(message="Hidden notice.", is_active=False)

        self.assertNotContains(self.client.get("/"), "Hidden notice.")

    def test_static_pages_hide_feed_filters_but_keep_site_search(self):
        for path in ("/about/", "/publications/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'class="filter-bar"')
                self.assertNotContains(response, 'aria-label="Article feeds"')
                self.assertContains(response, 'class="site-search"')

        feed_response = self.client.get("/")
        self.assertContains(feed_response, 'class="filter-bar"')
        self.assertContains(feed_response, 'aria-label="Article feeds"')

    def test_admin_can_edit_notice(self):
        notice = FrontPageNotice.objects.create(message="Existing notice.")
        admin = get_user_model().objects.create_superuser("notice-admin", "notice@example.com", "pw")
        self.client.force_login(admin)

        response = self.client.get(f"/backdoor/website/frontpagenotice/{notice.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existing notice.")
