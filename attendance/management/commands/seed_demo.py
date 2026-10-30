"""
Deneme verisi oluşturur: `python manage.py seed_demo`

Bir demo öğretmen, iki ders ve son 8 haftanın yoklamalarını ekler; böylece
istatistik ekranı ilk açılışta dolu görünür. Tüm isimler uydurmadır.
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from attendance.models import AttendanceRecord, AttendanceSession, Course

STUDENTS = [
    ("İrem", "Şahin"),
    ("Mert", "Yılmaz"),
    ("Zeynep", "Kaya"),
    ("Can", "Öztürk"),
    ("Elif", "Demir"),
    ("Burak", "Çelik"),
    ("Selin", "Aydın"),
    ("Emre", "Koç"),
    ("Deniz", "Arslan"),
    ("Ayşe", "Güneş"),
]


class Command(BaseCommand):
    help = "Demo öğretmen hesabı ve örnek yoklama verisi oluşturur."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo-sifre-2026")

    @transaction.atomic
    def handle(self, *args, username, password, **options):
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"“{username}” zaten var, işlem yapılmadı."))
            return

        teacher = user_model.objects.create_user(username=username, password=password)
        course = Course.objects.create(teacher=teacher, name="Veri Yapıları", code="BIL201")
        Course.objects.create(teacher=teacher, name="Web Programlama", code="BIL305")

        rng = random.Random(42)  # noqa: S311 - kriptografik değil, sadece demo verisi
        now = timezone.now()
        for week in range(8, 0, -1):
            started = now - timedelta(weeks=week)
            session = AttendanceSession.objects.create(
                course=course,
                started_at=started,
                ends_at=started + timedelta(minutes=15),
                closed_at=started + timedelta(minutes=15),
            )
            for i, (first, last) in enumerate(STUDENTS):
                # İlk altı öğrenci düzenli, son dördü sık devamsızlık yapıyor.
                if rng.random() < (0.95 if i < 6 else 0.5):
                    AttendanceRecord.objects.create(
                        session=session,
                        student_number=str(2022100 + i),
                        first_name=first,
                        last_name=last,
                    )

        self.stdout.write(self.style.SUCCESS(f"Demo hazır. Kullanıcı adı: {username}  Şifre: {password}"))
