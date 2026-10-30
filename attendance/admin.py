from django.contrib import admin

from .models import AttendanceRecord, AttendanceSession, Course


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "teacher", "created_at")
    search_fields = ("name", "code")


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0
    fields = ("student_number", "first_name", "last_name", "created_at")
    readonly_fields = ("created_at",)


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("course", "started_at", "ends_at", "closed_at")
    list_filter = ("course",)
    exclude = ("token", "token_expires_at")
    inlines = [AttendanceRecordInline]


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("student_number", "first_name", "last_name", "session", "created_at")
    search_fields = ("student_number", "first_name", "last_name")
    list_filter = ("session__course",)
