from django.db import models
import uuid
from django.utils import timezone
from datetime import timedelta

class AttendanceSession(models.Model):
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    token_expires_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def refresh_token(self):
        self.token = uuid.uuid4()
        self.expires_at = timezone.now() + timezone.timedelta(seconds=10)
        self.save()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Session {self.id} - Active: {self.is_active}"


class AttendanceRecord(models.Model):
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student_number = models.CharField(max_length=20)
    student_name = models.CharField(max_length=100)
    student_surname = models.CharField(max_length=100, default="Unknown")
    created_at = models.DateTimeField(auto_now_add=True)
    timestamp = models.DateTimeField(default=timezone.now)
    device_id = models.CharField(max_length=100, blank=True, null=True)
    class Meta:
        unique_together = ("session", "student_number")
        # aynı cihaz aynı session’da bir daha kullanılamasın
        constraints = [
            models.UniqueConstraint(fields=['session', 'device_id'], name='unique_device_per_session')
        ]
    def __str__(self):
        return f"{self.student_name} {self.student_surname}({self.student_number}) - Session {self.session.id}"
