"""Testlerde tekrar tekrar kullanılan küçük yardımcılar."""

from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from attendance.models import AttendanceRecord, AttendanceSession, Course

PASSWORD = "güçlü-Şifre-123"


def make_teacher(username="hoca"):
    return User.objects.create_user(username=username, password=PASSWORD)


def make_course(teacher, **kwargs):
    defaults = {"name": "Veri Yapıları", "code": "BIL201"}
    defaults.update(kwargs)
    return Course.objects.create(teacher=teacher, **defaults)


def make_session(course, minutes=15, **kwargs):
    now = timezone.now()
    return AttendanceSession.objects.create(
        course=course, started_at=now, ends_at=now + timedelta(minutes=minutes), **kwargs
    )


def make_record(session, number="2022001", **kwargs):
    defaults = {"first_name": "İrem", "last_name": "Şahin"}
    defaults.update(kwargs)
    return AttendanceRecord.objects.create(session=session, student_number=number, **defaults)
