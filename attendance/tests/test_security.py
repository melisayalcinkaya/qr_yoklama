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


class ClientIpTests(TestCase):
    def setUp(self):
        from django.test import RequestFactory

        self.factory = RequestFactory()

    def ip(self, **meta):
        from attendance.security import get_client_ip

        return get_client_ip(self.factory.get("/", **meta))

    def test_without_proxy_uses_remote_addr(self):
        self.assertEqual(self.ip(REMOTE_ADDR="1.1.1.1", HTTP_X_FORWARDED_FOR="9.9.9.9"), "1.1.1.1")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_behind_proxy_uses_forwarded_address(self):
        self.assertEqual(self.ip(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="5.5.5.5"), "5.5.5.5")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_spoofed_forwarded_header_is_ignored(self):
        # Saldırgan başlığa sahte bir IP yazar; proxy gerçek IP'yi sona ekler.
        self.assertEqual(self.ip(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.5.5.5"), "5.5.5.5")


class DemoModeTests(TestCase):
    @override_settings(DEMO_MODE=True)
    def test_login_shows_demo_credentials_in_demo_mode(self):
        self.assertContains(self.client.get(reverse("login")), "Demo hesabı")

    def test_login_hides_demo_credentials_by_default(self):
        self.assertNotContains(self.client.get(reverse("login")), "Demo hesabı")
