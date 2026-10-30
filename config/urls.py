from django.contrib import admin
from django.urls import include, path

from attendance import views as attendance_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/signup/", attendance_views.signup, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("attendance.urls")),
]
