import io

import openpyxl
from django.test import TestCase
from django.urls import reverse

from attendance.models import AttendanceSession, Course

from .factories import make_course, make_record, make_session, make_teacher


class AuthenticationRequiredTests(TestCase):
    """Öğretmen sayfaları giriş yapmamış kişiye açılmamalı."""

    def setUp(self):
        course = make_course(make_teacher())
        session = make_session(course)
        record = make_record(session)
        self.get_urls = [
            reverse("dashboard"),
            reverse("course_detail", args=[course.pk]),
            reverse("course_settings", args=[course.pk]),
            reverse("course_stats", args=[course.pk]),
            reverse("course_stats_export", args=[course.pk]),
            reverse("session_live", args=[session.pk]),
            reverse("session_records", args=[session.pk]),
            reverse("session_refresh_qr", args=[session.pk]),
            reverse("session_export", args=[session.pk]),
        ]
        self.post_urls = [
            reverse("course_create"),
            reverse("session_start", args=[course.pk]),
            reverse("session_close", args=[session.pk]),
            reverse("record_delete", args=[record.pk]),
        ]

    def test_anonymous_user_is_redirected_to_login(self):
        for url in self.get_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)
        for url in self.post_urls:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)


class OwnershipTests(TestCase):
    """Bir öğretmen başka öğretmenin verisine hiçbir şekilde erişememeli."""

    def setUp(self):
        owner = make_teacher("sahip")
        self.course = make_course(owner)
        self.session = make_session(self.course)
        self.record = make_record(self.session)
        self.client.force_login(make_teacher("baska"))

    def test_other_teacher_gets_404_everywhere(self):
        urls = [
            ("get", reverse("course_detail", args=[self.course.pk])),
            ("get", reverse("course_settings", args=[self.course.pk])),
            ("get", reverse("course_stats", args=[self.course.pk])),
            ("get", reverse("course_stats_export", args=[self.course.pk])),
            ("get", reverse("session_live", args=[self.session.pk])),
            ("get", reverse("session_records", args=[self.session.pk])),
            ("get", reverse("session_export", args=[self.session.pk])),
            ("post", reverse("session_start", args=[self.course.pk])),
            ("get", reverse("session_refresh_qr", args=[self.session.pk])),
            ("post", reverse("session_close", args=[self.session.pk])),
            ("post", reverse("record_delete", args=[self.record.pk])),
        ]
        for method, url in urls:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)

    def test_other_teacher_cannot_delete_or_close(self):
        self.client.post(reverse("record_delete", args=[self.record.pk]))
        self.client.post(reverse("session_close", args=[self.session.pk]))
        self.session.refresh_from_db()
        self.assertTrue(self.session.records.exists())
        self.assertTrue(self.session.is_active)

    def test_dashboard_shows_only_own_courses(self):
        make_course(self.course.teacher, name="Gizli Ders")
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "Gizli Ders")


class CourseAndSessionFlowTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.client.force_login(self.teacher)

    def test_create_course(self):
        response = self.client.post(reverse("course_create"), {"name": "Algoritmalar", "code": "BIL202"})
        course = Course.objects.get(name="Algoritmalar")
        self.assertEqual(course.teacher, self.teacher)
        self.assertRedirects(response, reverse("course_detail", args=[course.pk]))

    def test_start_session_closes_previous_active_session(self):
        course = make_course(self.teacher)
        old = make_session(course)
        self.client.post(reverse("session_start", args=[course.pk]), {"duration_minutes": 10})
        old.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertEqual(AttendanceSession.objects.active().filter(course=course).count(), 1)

    def test_invalid_duration_is_rejected(self):
        course = make_course(self.teacher)
        self.client.post(reverse("session_start", args=[course.pk]), {"duration_minutes": 0})
        self.assertFalse(course.sessions.exists())

    def test_refresh_qr_returns_current_code_and_countdown(self):
        session = make_session(make_course(self.teacher))
        data = self.client.get(reverse("session_refresh_qr", args=[session.pk])).json()
        self.assertTrue(data["active"])
        self.assertTrue(data["qr_code_b64"])
        self.assertTrue(0 < data["seconds_left"] <= 5)

    def test_refresh_qr_of_closed_session(self):
        session = make_session(make_course(self.teacher))
        session.close()
        data = self.client.get(reverse("session_refresh_qr", args=[session.pk])).json()
        self.assertFalse(data["active"])

    def test_records_endpoint_returns_only_new_records(self):
        session = make_session(make_course(self.teacher))
        first = make_record(session, number="1")
        make_record(session, number="2")
        url = reverse("session_records", args=[session.pk])
        data = self.client.get(url, {"after": first.pk}).json()
        self.assertEqual(data["total"], 2)
        self.assertEqual([r["number"] for r in data["records"]], ["2"])

    def test_teacher_can_delete_record(self):
        session = make_session(make_course(self.teacher))
        record = make_record(session)
        self.client.post(reverse("record_delete", args=[record.pk]))
        self.assertFalse(session.records.exists())

    def test_location_settings_require_coordinates(self):
        course = make_course(self.teacher)
        url = reverse("course_settings", args=[course.pk])
        self.client.post(url, {"name": "X", "location_enabled": "on", "radius_m": 100})
        course.refresh_from_db()
        self.assertFalse(course.location_enabled)
        self.client.post(
            url, {"name": "X", "location_enabled": "on", "latitude": 37.9, "longitude": 29.1, "radius_m": 100}
        )
        course.refresh_from_db()
        self.assertTrue(course.location_enabled)


class ExportTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.client.force_login(self.teacher)
        self.session = make_session(make_course(self.teacher))

    def _sheet_rows(self, response):
        wb = openpyxl.load_workbook(io.BytesIO(response.content))
        return list(wb.active.iter_rows(values_only=True))

    def test_session_export_contains_records(self):
        make_record(self.session, number="2022001")
        rows = self._sheet_rows(self.client.get(reverse("session_export", args=[self.session.pk])))
        self.assertEqual(rows[0][:3], ("Ad", "Soyad", "Numara"))
        self.assertEqual(rows[1][2], "2022001")

    def test_excel_formula_injection_is_neutralised(self):
        make_record(self.session, first_name='=HYPERLINK("http://kotu.site","tikla")')
        rows = self._sheet_rows(self.client.get(reverse("session_export", args=[self.session.pk])))
        self.assertTrue(rows[1][0].startswith("'="))


class StatsTests(TestCase):
    def setUp(self):
        self.teacher = make_teacher()
        self.client.force_login(self.teacher)
        self.course = make_course(self.teacher)

    def test_attendance_rates(self):
        sessions = [make_session(self.course) for _ in range(4)]
        for s in sessions:
            make_record(s, number="1")  # 4/4 -> %100
        make_record(sessions[0], number="2")  # 1/4 -> %25
        response = self.client.get(reverse("course_stats", args=[self.course.pk]))
        students = {s["number"]: s for s in response.context["students"]}
        self.assertEqual(response.context["total_sessions"], 4)
        self.assertEqual(students["1"]["rate"], 100)
        self.assertFalse(students["1"]["at_risk"])
        self.assertEqual(students["2"]["rate"], 25)
        self.assertEqual(students["2"]["missed"], 3)
        self.assertTrue(students["2"]["at_risk"])
        self.assertEqual(response.context["at_risk_count"], 1)

    def test_stats_page_without_data(self):
        response = self.client.get(reverse("course_stats", args=[self.course.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["students"], [])
