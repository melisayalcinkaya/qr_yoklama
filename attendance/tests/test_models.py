import time
from datetime import timedelta
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from attendance.geo import haversine_m, is_within_radius
from attendance.models import QR_ROTATE_SECONDS, QR_VALID_WINDOWS

from .factories import make_course, make_record, make_session, make_teacher


class AttendanceSessionTests(TestCase):
    def setUp(self):
        self.session = make_session(make_course(make_teacher()))
        # Pencere sınırına denk gelip testlerin rastgele kırılmaması için
        # "şimdi"yi bir pencerenin tam başına sabitliyoruz.
        self.now = (time.time() // QR_ROTATE_SECONDS) * QR_ROTATE_SECONDS

    def test_new_session_is_active(self):
        self.assertTrue(self.session.is_active)

    def test_session_is_inactive_after_end_time(self):
        self.session.ends_at = timezone.now() - timedelta(seconds=1)
        self.assertFalse(self.session.is_active)

    def test_closed_session_is_inactive(self):
        self.session.close()
        self.assertFalse(self.session.is_active)
        self.assertIsNotNone(self.session.closed_at)

    def at(self, seconds_from_now):
        """time.time()'ı ileri sarmak için yardımcı."""
        return mock.patch("attendance.models.time.time", return_value=self.now + seconds_from_now)

    def test_current_token_is_valid(self):
        self.assertTrue(self.session.is_token_valid(self.session.current_token()))

    def test_wrong_or_missing_token_is_invalid(self):
        self.assertFalse(self.session.is_token_valid("yanlis-token"))
        self.assertFalse(self.session.is_token_valid(""))
        self.assertFalse(self.session.is_token_valid(None))

    def test_token_changes_every_rotation(self):
        with self.at(0):
            first = self.session.current_token()
        with self.at(QR_ROTATE_SECONDS):
            self.assertNotEqual(first, self.session.current_token())

    def test_previous_code_still_valid_after_rotation(self):
        """Hata düzeltmesi: ekran yenilendiği anda okutulmakta olan kod geçersiz olmamalı."""
        with self.at(0):
            shown = self.session.current_token()
        with self.at(QR_ROTATE_SECONDS * (QR_VALID_WINDOWS - 1)):
            self.assertTrue(self.session.is_token_valid(shown))

    def test_token_expires_after_valid_windows(self):
        with self.at(0):
            shown = self.session.current_token()
        with self.at(QR_ROTATE_SECONDS * QR_VALID_WINDOWS):
            self.assertFalse(self.session.is_token_valid(shown))

    def test_token_of_closed_session_is_invalid(self):
        token = self.session.current_token()
        self.session.close()
        self.assertFalse(self.session.is_token_valid(token))

    def test_tokens_are_unique_per_session(self):
        other = make_session(self.session.course)
        with self.at(0):
            self.assertNotEqual(self.session.current_token(), other.current_token())

    def test_token_from_another_session_is_rejected(self):
        other = make_session(self.session.course)
        self.assertFalse(self.session.is_token_valid(other.current_token()))


class AttendanceRecordConstraintTests(TestCase):
    def setUp(self):
        self.session = make_session(make_course(make_teacher()))

    def test_same_student_cannot_check_in_twice(self):
        make_record(self.session, number="1")
        with self.assertRaises(IntegrityError):
            make_record(self.session, number="1")

    def test_same_device_cannot_be_used_twice(self):
        make_record(self.session, number="1", device_id="cihaz")
        with self.assertRaises(IntegrityError):
            make_record(self.session, number="2", device_id="cihaz")

    def test_records_without_device_id_are_allowed(self):
        make_record(self.session, number="1", device_id=None)
        make_record(self.session, number="2", device_id=None)
        self.assertEqual(self.session.records.count(), 2)

    def test_same_student_can_attend_different_sessions(self):
        other = make_session(self.session.course)
        make_record(self.session, number="1")
        make_record(other, number="1")


class GeoTests(TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(haversine_m(37.9, 29.1, 37.9, 29.1), 0)

    def test_known_distance(self):
        # Pamukkale travertenleri ile Denizli merkezi arası yaklaşık 15,5 km.
        distance = haversine_m(37.9137, 29.1187, 37.7765, 29.0864)
        self.assertAlmostEqual(distance / 1000, 15.5, delta=0.3)

    def test_inside_radius(self):
        inside, _ = is_within_radius(37.9137, 29.1187, 100, 37.9140, 29.1190, 10)
        self.assertTrue(inside)

    def test_outside_radius(self):
        inside, distance = is_within_radius(37.9137, 29.1187, 100, 37.92, 29.13, 10)
        self.assertFalse(inside)
        self.assertGreater(distance, 100)

    def test_gps_accuracy_is_tolerated(self):
        # ~130 m uzakta ama telefon ±50 m hata payı bildiriyor -> kabul.
        inside, _ = is_within_radius(37.9137, 29.1187, 100, 37.9149, 29.1187, 50)
        self.assertTrue(inside)
