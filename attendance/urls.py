from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("courses/new/", views.course_create, name="course_create"),
    path("courses/<int:pk>/", views.course_detail, name="course_detail"),
    path("courses/<int:pk>/start/", views.session_start, name="session_start"),
    path("sessions/<int:pk>/", views.session_live, name="session_live"),
    path("sessions/<int:pk>/qr/", views.session_refresh_qr, name="session_refresh_qr"),
    path("sessions/<int:pk>/records/", views.session_records, name="session_records"),
    path("sessions/<int:pk>/close/", views.session_close, name="session_close"),
    path("records/<int:pk>/delete/", views.record_delete, name="record_delete"),
    path("sessions/<int:pk>/export/", views.session_export, name="session_export"),
    # Öğrencinin QR ile açtığı adres; kısa tutuldu ki QR kod sade olsun.
    path("c/<int:pk>/", views.checkin, name="checkin"),
]
