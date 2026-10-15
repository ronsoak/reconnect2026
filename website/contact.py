# ===== ===== ===== ===== ===== ===== ===== =====
# Contact form protection and delivery
# ===== ===== ===== ===== ===== ===== ===== =====
# The About-page contact form is guarded by several layers, cheapest first:
#
#   1. Honeypot      - a hidden "website" field people never see. Bots that fill
#                      every input get a fake success and nothing is saved.
#   2. Signed timer  - the form carries a signed timestamp. Submissions faster
#                      than CONTACT_MIN_SECONDS or older than CONTACT_MAX_AGE are
#                      rejected, and the signature stops bots forging it.
#   3. Rate limit    - each visitor can send CONTACT_RATE_LIMIT messages per hour.
#                      The cache key is a keyed hash of the IP; no IP is stored.
#   4. Turnstile     - Cloudflare's challenge token is verified server-side.
#
# Saved messages appear in the admin under "Contact messages". Each one also
# triggers an email to CONTACT_EMAIL; a failed email never loses the message.
#
# Settings (all read from environment variables in reconnect/settings.py):
#   TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY  - from the Cloudflare dashboard
#   CONTACT_EMAIL                              - where notifications are sent
#   CLIENT_IP_HEADER                           - e.g. HTTP_X_REAL_IP behind a proxy
import hashlib
import hmac
import logging
import time

import requests
from django import forms
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMessage

from .models import ContactMessage

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMESTAMP_SALT = "website.contact.started"
RATE_WINDOW_SECONDS = 60 * 60


class ContactForm(forms.ModelForm):
    # Honeypot: hidden from people with CSS and aria-hidden, left for bots.
    website = forms.CharField(required=False, label="Leave this field empty")
    # Signed time the form was rendered, checked in clean().
    started = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "reason", "message"]
        widgets = {"reason": forms.RadioSelect}
        error_messages = {
            "name": {"required": "Please enter your name."},
            "email": {
                "required": "Please enter your email address.",
                "invalid": "Please enter a valid email address.",
            },
            "reason": {"required": "Please choose a reason for getting in touch."},
            "message": {"required": "Please enter a message."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Unbound forms get a fresh signed timestamp each time they render.
        if not self.is_bound:
            self.initial["started"] = signing.dumps(time.time(), salt=TIMESTAMP_SALT)
        self.fields["reason"].choices = ContactMessage.REASON_CHOICES

    @property
    def is_honeypot_filled(self):
        return bool(self.data.get("website", "").strip())

    def clean_name(self):
        name = self.cleaned_data["name"]
        # Newlines would break the email subject header, so refuse them.
        if "\n" in name or "\r" in name:
            raise forms.ValidationError("Please enter your name on one line.")
        return name

    def clean(self):
        cleaned = super().clean()
        try:
            started = signing.loads(
                self.data.get("started", ""),
                salt=TIMESTAMP_SALT,
                max_age=settings.CONTACT_MAX_AGE,
            )
        except signing.SignatureExpired:
            raise forms.ValidationError("This form expired. Please send your message again.")
        except signing.BadSignature:
            raise forms.ValidationError("Something went wrong. Please reload the page and try again.")
        if time.time() - float(started) < settings.CONTACT_MIN_SECONDS:
            raise forms.ValidationError("That was very quick. Please wait a moment and send again.")
        if time.time() - float(started) > settings.CONTACT_MAX_AGE:
            raise forms.ValidationError("This form expired. Please send your message again.")
        return cleaned


def client_ip(request):
    # Behind Railway's proxy REMOTE_ADDR is the proxy, so a trusted header can be
    # named in CLIENT_IP_HEADER. Only set it when the proxy overwrites that header.
    header = settings.CLIENT_IP_HEADER
    if header:
        value = request.META.get(header, "").split(",")[0].strip()
        if value:
            return value
    return request.META.get("REMOTE_ADDR", "")


def rate_limit_key(request):
    digest = hmac.new(
        settings.SECRET_KEY.encode(), client_ip(request).encode(), hashlib.sha256
    ).hexdigest()
    return f"contact-rate:{digest}"


def is_rate_limited(request):
    return cache.get(rate_limit_key(request), 0) >= settings.CONTACT_RATE_LIMIT


def record_submission(request):
    key = rate_limit_key(request)
    # add() only sets the expiry for the first message in the window.
    if not cache.add(key, 1, RATE_WINDOW_SECONDS):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, RATE_WINDOW_SECONDS)


def turnstile_enabled():
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


def verify_turnstile(request):
    # Without keys the check is skipped in DEBUG so local development works.
    # In production missing keys fail closed rather than letting bots through.
    if not turnstile_enabled():
        if settings.DEBUG:
            return True
        logger.error("Contact form rejected: Turnstile keys are not configured.")
        return False

    token = request.POST.get("cf-turnstile-response", "")
    if not token or len(token) > 2048:
        return False
    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": client_ip(request),
            },
            timeout=10,
        )
        result = response.json()
    except (requests.RequestException, ValueError):
        logger.exception("Turnstile verification request failed.")
        return False
    if not result.get("success"):
        logger.info("Turnstile rejected a contact message: %s", result.get("error-codes"))
        return False
    return True


def send_notification(contact):
    # Reply-To is the visitor, so replying from the inbox answers them directly.
    email = EmailMessage(
        subject=f"[Reconnect] {contact.get_reason_display()} from {contact.name}",
        body=(
            f"Name: {contact.name}\n"
            f"Email: {contact.email}\n"
            f"Reason: {contact.get_reason_display()}\n\n"
            f"{contact.message}\n"
        ),
        to=[settings.CONTACT_EMAIL],
        reply_to=[contact.email],
    )
    try:
        email.send()
    except Exception:
        logger.exception("Contact notification email failed for message %s.", contact.pk)
        return False
    ContactMessage.objects.filter(pk=contact.pk).update(email_sent=True)
    return True
