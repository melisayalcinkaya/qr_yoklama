import secrets
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

# QR kodun içindeki token bu süre boyunca geçerlidir. Panel QR'ı bundan
# daha sık yeniler; böylece ekran görüntüsüyle paylaşılan bir QR kısa
# sürede işe yaramaz hale gelir.
TOKEN_LIFETIME = timedelta(seconds=15)
DEFAULT_SESSION_DURATION = timedelta(minutes=15)


def new_token() -> str:
    # secrets modülü kriptografik olarak güvenli rastgele değer üretir;
    # random modülü tahmin edilebilir olduğu için güvenlik işlerinde kullanılmaz.
    return secrets.token_urlsafe(16)


class Course(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courses")
    name = models.CharField("Ders adı", max_length=120)
    code = models.CharField("Ders kodu", max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Konum doğrulama (opsiyonel): açıksa öğrencinin sınıfa yakın olması gerekir.
    location_enabled = models.BooleanField("Konum doğrulaması", default=False)
    latitude = models.FloatField("Enlem", null=True, blank=True)
    longitude = models.FloatField("Boylam", null=True, blank=True)
    radius_m = models.PositiveIntegerField(
        "İzin verilen yarıçap (metre)",
        default=100,
        validators=[MinValueValidator(20), MaxValueValidator(2000)],
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Ders"
        verbose_name_plural = "Dersler"

    def __str__(self):
        return f"{self.code} {self.name}".strip()


class AttendanceSessionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(closed_at__isnull=True, ends_at__gt=timezone.now())


class AttendanceSession(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    started_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=64, default=new_token)
    token_expires_at = models.DateTimeField()

    objects = AttendanceSessionQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Yoklama oturumu"
        verbose_name_plural = "Yoklama oturumları"

    def __str__(self):
        return f"{self.course} - {timezone.localtime(self.started_at):%d.%m.%Y %H:%M}"

    def save(self, *args, **kwargs):
        now = timezone.now()
        if not self.ends_at:
            self.ends_at = (self.started_at or now) + DEFAULT_SESSION_DURATION
        if not self.token_expires_at:
            self.token_expires_at = now + TOKEN_LIFETIME
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        return self.closed_at is None and timezone.now() < self.ends_at

    def rotate_token(self) -> None:
        self.token = new_token()
        self.token_expires_at = timezone.now() + TOKEN_LIFETIME
        self.save(update_fields=["token", "token_expires_at"])

    def is_token_valid(self, token: str | None) -> bool:
        if not token or not self.is_active:
            return False
        if timezone.now() > self.token_expires_at:
            return False
        # compare_digest, karşılaştırma süresinden bilgi sızmasını (timing attack) önler.
        return secrets.compare_digest(token, self.token)

    def close(self) -> None:
        if self.closed_at is None:
            self.closed_at = timezone.now()
            self.save(update_fields=["closed_at"])


class AttendanceRecord(models.Model):
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student_number = models.CharField("Öğrenci numarası", max_length=20)
    first_name = models.CharField("Ad", max_length=100)
    last_name = models.CharField("Soyad", max_length=100)
    # Normalde CharField'da null=True önerilmez (boş değer için "" kullanılır).
    # Burada bilinçli: (session, device_id) benzersiz olduğu için cihaz kimliği
    # olmayan kayıtlar "" olsaydı birbiriyle çakışırdı; NULL'lar çakışmaz.
    device_id = models.CharField(max_length=64, blank=True, null=True)  # noqa: DJ001
    # Konum doğrulaması açıksa öğrencinin sınıfa uzaklığı (metre) saklanır.
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Yoklama kaydı"
        verbose_name_plural = "Yoklama kayıtları"
        constraints = [
            models.UniqueConstraint(fields=["session", "student_number"], name="unique_student_per_session"),
            models.UniqueConstraint(fields=["session", "device_id"], name="unique_device_per_session"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.student_number})"
