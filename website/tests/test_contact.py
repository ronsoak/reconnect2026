import time
from unittest import mock

import requests
from django.core import mail, signing
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from website.contact import TIMESTAMP_SALT
from website.models import ContactMessage

TURNSTILE_KEYS = {
    "TURNSTILE_SITE_KEY": "1x00000000000000000000AA",
    "TURNSTILE_SECRET_KEY": "1x0000000000000000000000000000000AA",
}


def signed_start(seconds_ago=10):
    return signing.dumps(time.time() - seconds_ago, salt=TIMESTAMP_SALT)


def turnstile_reply(success):
    response = mock.Mock()
    response.json.return_value = {"success": success, "error-codes": [] if success else ["invalid-input-response"]}
    return response


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CONTACT_EMAIL="alex@antranaut.com",
    CONTACT_RATE_LIMIT=3,
    **TURNSTILE_KEYS,
)
class ContactFormTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("contact")
        patcher = mock.patch("website.contact.requests.post", return_value=turnstile_reply(True))
        self.turnstile = patcher.start()
        self.addCleanup(patcher.stop)

    def payload(self, **overrides):
        data = {
            "name": "Sam Reader",
            "email": "sam@example.com",
            "reason": "SUGGEST_SITE",
            "message": "You should follow this blog.",
            "started": signed_start(),
            "website": "",
            "cf-turnstile-response": "token",
        }
        data.update(overrides)
        return data

    def test_about_page_shows_contact_form_and_turnstile(self):
        response = self.client.get(reverse("about"))
        self.assertContains(response, 'id="contact"')
        self.assertContains(response, 'action="/about/contact/#contact"')
        for label in ("Advertising", "Suggest a site", "Other"):
            self.assertContains(response, label)
        self.assertContains(response, 'name="website"')
        self.assertContains(response, TURNSTILE_KEYS["TURNSTILE_SITE_KEY"])
        self.assertContains(response, "challenges.cloudflare.com/turnstile/v0/api.js")

    def test_turnstile_script_only_loads_on_about(self):
        response = self.client.get(reverse("privacy"))
        self.assertNotContains(response, "challenges.cloudflare.com")

    def test_valid_message_is_saved_and_emailed(self):
        response = self.client.post(self.url, self.payload())
        self.assertRedirects(response, reverse("about") + "?sent=1#contact", fetch_redirect_response=False)
        contact = ContactMessage.objects.get()
        self.assertEqual(contact.reason, "SUGGEST_SITE")
        self.assertTrue(contact.email_sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alex@antranaut.com"])
        self.assertEqual(mail.outbox[0].reply_to, ["sam@example.com"])
        self.assertIn("Suggest a site from Sam Reader", mail.outbox[0].subject)
        self.assertEqual(self.turnstile.call_args.kwargs["data"]["response"], "token")

    def test_success_notice_after_redirect(self):
        response = self.client.get(reverse("about") + "?sent=1")
        self.assertContains(response, "your message has been sent")

    def test_honeypot_fakes_success_without_saving(self):
        response = self.client.post(self.url, self.payload(website="http://spam.example"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        self.turnstile.assert_not_called()

    def test_too_fast_submission_is_rejected(self):
        response = self.client.post(self.url, self.payload(started=signed_start(seconds_ago=0)))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "very quick", status_code=400)
        self.assertFalse(ContactMessage.objects.exists())

    def test_forged_or_missing_timestamp_is_rejected(self):
        for started in ("", str(time.time() - 60), "forged:value"):
            with self.subTest(started=started):
                response = self.client.post(self.url, self.payload(started=started))
                self.assertEqual(response.status_code, 400)
        self.assertFalse(ContactMessage.objects.exists())

    def test_expired_form_is_rejected(self):
        response = self.client.post(self.url, self.payload(started=signed_start(seconds_ago=60 * 60 * 3)))
        self.assertContains(response, "expired", status_code=400)

    def test_failed_turnstile_is_rejected(self):
        self.turnstile.return_value = turnstile_reply(False)
        response = self.client.post(self.url, self.payload())
        self.assertContains(response, "confirm you&#x27;re human", status_code=400)
        self.assertFalse(ContactMessage.objects.exists())

    def test_turnstile_network_error_fails_closed(self):
        self.turnstile.side_effect = requests.ConnectionError
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ContactMessage.objects.exists())

    def test_missing_token_is_rejected_without_calling_cloudflare(self):
        response = self.client.post(self.url, self.payload(**{"cf-turnstile-response": ""}))
        self.assertEqual(response.status_code, 400)
        self.turnstile.assert_not_called()

    def test_rate_limit_after_three_messages(self):
        for _ in range(3):
            self.assertEqual(self.client.post(self.url, self.payload()).status_code, 302)
        response = self.client.post(self.url, self.payload())
        self.assertContains(response, "try again in an hour", status_code=429)
        self.assertEqual(ContactMessage.objects.count(), 3)

    def test_rate_limit_is_per_visitor(self):
        for _ in range(3):
            self.client.post(self.url, self.payload(), REMOTE_ADDR="10.0.0.1")
        response = self.client.post(self.url, self.payload(), REMOTE_ADDR="10.0.0.2")
        self.assertEqual(response.status_code, 302)

    def test_required_fields_and_reason_choice(self):
        response = self.client.post(self.url, self.payload(name="", email="not-an-email", reason="SPAM", message=""))
        self.assertEqual(response.status_code, 400)
        for text in ("Please enter your name.", "Please enter a valid email address.", "Please enter a message.", "Select a valid choice"):
            self.assertContains(response, text, status_code=400)
        self.assertContains(response, 'aria-invalid="true"', status_code=400)
        self.assertFalse(ContactMessage.objects.exists())

    def test_name_with_newline_is_rejected(self):
        response = self.client.post(self.url, self.payload(name="Sam\nBcc: x@example.com"))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ContactMessage.objects.exists())

    def test_overlong_message_is_rejected(self):
        response = self.client.post(self.url, self.payload(message="x" * 5001))
        self.assertEqual(response.status_code, 400)

    def test_entered_values_are_kept_after_an_error(self):
        response = self.client.post(self.url, self.payload(message=""))
        self.assertContains(response, 'value="Sam Reader"', status_code=400)
        self.assertContains(response, 'value="SUGGEST_SITE"\n                   checked', status_code=400)

    def test_email_failure_still_saves_message(self):
        with mock.patch("website.contact.EmailMessage.send", side_effect=OSError("SMTP down")):
            response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        contact = ContactMessage.objects.get()
        self.assertFalse(contact.email_sent)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_csrf_is_enforced(self):
        client = self.client_class(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, self.payload()).status_code, 403)


@override_settings(TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY="", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ContactWithoutTurnstileKeysTests(TestCase):
    def setUp(self):
        cache.clear()

    def payload(self):
        return {
            "name": "Sam", "email": "sam@example.com", "reason": "OTHER",
            "message": "Hello", "started": signed_start(), "website": "",
        }

    @override_settings(DEBUG=True)
    def test_debug_skips_turnstile(self):
        self.assertNotContains(self.client.get(reverse("about")), "challenges.cloudflare.com")
        response = self.client.post(reverse("contact"), self.payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ContactMessage.objects.exists())

    @override_settings(DEBUG=False)
    def test_production_without_keys_fails_closed(self):
        response = self.client.post(reverse("contact"), self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ContactMessage.objects.exists())
