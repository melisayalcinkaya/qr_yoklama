"""
Öğrencinin QR okutup yoklama verdiği akışın testleri.
Projenin asıl güvenlik vaadi burada olduğu için en kapsamlı testler bunlar.
"""

import time
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from attendance import views
from attendance.models import QR_ROTATE_SECONDS, QR_VALID_WINDOWS

from .factories import make_course, make_record, make_session, make_teacher

VALID_FORM = {"first_name": "İrem", "last_name": "Şahin", "student_number": "2022001", "device_id": "cihaz-1"}


class CheckinFlowTests(TestCase):
    def setUp(self):
        self.course = make_course(make_teacher())
        self.session = make_session(self.course)
        self.url = reverse("checkin", args=[self.session.pk])

    def scan(self, token=None):
        """QR okutmayı taklit eder."""
        return self.client.get(self.url, {"t": token or self.session.current_token()})

    def test_valid_scan_redirects_to_form_without_token_in_url(self):
        response = self.scan()
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_successful_checkin(self):
        self.scan()
        response = self.client.post(self.url, VALID_FORM)
        self.assertContains(response, "Yoklamanız alındı")
        record = self.session.records.get()
        self.assertEqual(record.first_name, "İrem")  # Türkçe karakterler korunuyor
        self.assertEqual(record.device_id, "cihaz-1")

    def test_form_cannot_be_opened_without_scanning(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_post_without_scanning_is_rejected(self):
        """Eski sürümdeki açık: oturum numarasını bilen herkes yoklama verebiliyordu."""
        response = self.client.post(self.url, VALID_FORM)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.session.records.exists())

    def test_wrong_token_is_rejected(self):
        self.assertEqual(self.scan("tahmin-edilen-token").status_code, 403)

    def test_expired_token_is_rejected(self):
        """Paylaşılan QR fotoğrafı, geçerlilik süresi dolunca işe yaramamalı."""
        shown = self.session.current_token()
        later = time.time() + QR_ROTATE_SECONDS * (QR_VALID_WINDOWS + 1)
        with mock.patch("attendance.models.time.time", return_value=later):
            self.assertEqual(self.scan(shown).status_code, 403)

    def test_code_scanned_right_after_rotation_is_accepted(self):
        """Kullanıcı hatası düzeltmesi: telefon kaldırılırken ekranda kod değişirse yine kabul edilmeli."""
        shown = self.session.current_token()
        later = time.time() + QR_ROTATE_SECONDS
        with mock.patch("attendance.models.time.time", return_value=later):
            self.assertEqual(self.scan(shown).status_code, 302)

    def test_grant_expires(self):
        self.scan()
        later = time.time() + views.CHECKIN_GRANT_SECONDS + 1
        with mock.patch("attendance.views.time.time", return_value=later):
            response = self.client.post(self.url, VALID_FORM)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.session.records.exists())

    def test_closed_session_rejects_checkin(self):
        self.session.close()
        self.assertEqual(self.scan().status_code, 410)

    def test_duplicate_student_number(self):
        make_record(self.session, number="2022001")
        self.scan()
        response = self.client.post(self.url, VALID_FORM)
        self.assertContains(response, "zaten yoklama alınmış")
        self.assertEqual(self.session.records.count(), 1)

    def test_duplicate_device(self):
        make_record(self.session, number="999", device_id="cihaz-1")
        self.scan()
        response = self.client.post(self.url, VALID_FORM)
        self.assertContains(response, "Bu cihazla")
        self.assertEqual(self.session.records.count(), 1)

    def test_student_number_must_be_digits(self):
        self.scan()
        response = self.client.post(self.url, {**VALID_FORM, "student_number": "12a4"})
        self.assertContains(response, "yalnızca rakamlardan")
        self.assertFalse(self.session.records.exists())

    def test_already_checked_in_browser_sees_done_page(self):
        self.scan()
        self.client.post(self.url, VALID_FORM)
        self.assertContains(self.client.get(self.url), "Yoklamanız alındı")

    def test_html_in_name_is_escaped(self):
        self.scan()
        self.client.post(self.url, {**VALID_FORM, "first_name": "<script>alert(1)</script>"})
        teacher = self.course.teacher
        self.client.force_login(teacher)
        response = self.client.get(reverse("course_stats", args=[self.course.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")


class LocationCheckinTests(TestCase):
    def setUp(self):
        self.course = make_course(
            make_teacher(), location_enabled=True, latitude=37.9137, longitude=29.1187, radius_m=100
        )
        self.session = make_session(self.course)
        self.url = reverse("checkin", args=[self.session.pk])
        self.client.get(self.url, {"t": self.session.current_token()})

    def post(self, **location):
        return self.client.post(self.url, {**VALID_FORM, **location})

    def test_location_is_required(self):
        response = self.post()
        self.assertContains(response, "konum izni gerekiyor")
        self.assertFalse(self.session.records.exists())

    def test_student_inside_classroom(self):
        self.post(latitude=37.9140, longitude=29.1190, accuracy=15)
        record = self.session.records.get()
        self.assertLess(record.distance_m, 100)

    def test_student_far_away(self):
        response = self.post(latitude=37.95, longitude=29.15, accuracy=15)
        self.assertContains(response, "Sınıfın dışında")
        self.assertFalse(self.session.records.exists())

    def test_low_accuracy_is_rejected(self):
        response = self.post(latitude=37.9140, longitude=29.1190, accuracy=1500)
        self.assertContains(response, "hassasiyeti çok düşük")
        self.assertFalse(self.session.records.exists())
