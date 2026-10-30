from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from attendance.models import Course

from .factories import PASSWORD, make_teacher


class LoginBruteForceTests(TestCase):
    def setUp(self):
        make_teacher("hoca")
        self.url = reverse("login")

    def test_account_is_locked_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(self.url, {"username": "hoca", "password": "yanlis"})
        # Doğru şifre bile artık kabul edilmemeli.
        response = self.client.post(self.url, {"username": "hoca", "password": PASSWORD})
        self.assertContains(response, "Çok fazla hatalı deneme", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_correct_password_logs_in(self):
        response = self.client.post(self.url, {"username": "hoca", "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboard"))


class SecurityHeaderTests(TestCase):
    def test_page_cannot_be_framed(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    @override_settings(DEBUG=False)
    def test_unknown_page_does_not_leak_debug_info(self):
        response = self.client.get("/olmayan-sayfa/")
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Traceback", status_code=404)
        self.assertNotContains(response, "urlpatterns", status_code=404)


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_creates_data_once(self):
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)  # ikinci kez çalıştırmak güvenli olmalı
        self.assertEqual(Course.objects.count(), 2)
        course = Course.objects.get(code="BIL201")
        self.assertEqual(course.sessions.count(), 8)
