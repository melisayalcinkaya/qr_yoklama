from django.urls import path
from . import views

urlpatterns = [
    path("generate_qr/", views.generate_qr, name="generate_qr"),
    path("refresh_qr/", views.refresh_qr, name="refresh_qr"),
    path("checkin/", views.checkin, name="checkin"),
    path("export/<int:session_id>/", views.export_attendance, name="export_attendance"),
    path("teacher_dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
]
