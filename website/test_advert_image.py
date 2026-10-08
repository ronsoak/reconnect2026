import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from website.models import Adverts, Logic

MEDIA = tempfile.mkdtemp()


def png_file(name="ad.png"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class AdvertImageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.size = Logic.objects.create(logic_type="AD_SIZE", value="Feed Small")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def make(self, **kwargs):
        today = timezone.localdate()
        return Adverts.objects.create(
            title="Ad", message="Try this", site_name="Blog", site_url="https://b.example.com",
            start_date=today, end_date=today + timedelta(days=1), concurrency=1,
            advert_size=self.size, **kwargs,
        )

    def test_image_is_optional(self):
        self.assertFalse(self.make().image)
        self.assertNotContains(self.client.get("/newest/"), "/media/adverts/")

    def test_image_shows_on_the_card_and_is_served(self):
        advert = self.make(image=png_file())
        response = self.client.get("/newest/")
        self.assertContains(response, advert.image.url)
        self.assertEqual(self.client.get(advert.image.url).status_code, 200)

    def test_api_gives_the_image_address_or_blank(self):
        advert = self.make(image=png_file())
        card = next(c for c in self.client.get("/api/feed/?feed=newest").json()["cards"] if c["kind"] == "advert")
        self.assertEqual(card["item"]["image"], advert.image.url)
        advert.image.delete()
        card = next(c for c in self.client.get("/api/feed/?feed=newest").json()["cards"] if c["kind"] == "advert")
        self.assertEqual(card["item"]["image"], "")
