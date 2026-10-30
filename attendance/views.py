import base64
import io
import time
from datetime import timedelta
from urllib.parse import urlencode

import openpyxl
import qrcode
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CheckinForm, CourseForm, StartSessionForm
from .models import AttendanceRecord, AttendanceSession, Course

# Öğrenci QR'ı okuttuktan sonra formu doldurmak için bu kadar süresi var.
CHECKIN_GRANT_SECONDS = 180


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _qr_png_base64(data: str) -> str:
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _checkin_url(request, session: AttendanceSession) -> str:
    path = reverse("checkin", args=[session.pk])
    return request.build_absolute_uri(f"{path}?{urlencode({'t': session.token})}")


def _excel_safe(value: str) -> str:
    """
    Formül enjeksiyonunu önler: "=HYPERLINK(...)" gibi bir ad girilirse Excel
    bunu formül olarak çalıştırır. Başına ' eklemek değeri düz metin yapar.
    """
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _get_own_session(request, pk: int) -> AttendanceSession:
    # Başka bir öğretmenin oturumuna erişmeye çalışan kişi 404 alır.
    # 403 yerine 404 dönmek, o kaydın var olup olmadığını da gizler.
    return get_object_or_404(
        AttendanceSession.objects.select_related("course"), pk=pk, course__teacher=request.user
    )


# ---------------------------------------------------------------------------
# Hesap
# ---------------------------------------------------------------------------

def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Hesabınız oluşturuldu. İlk dersinizi ekleyin.")
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


# ---------------------------------------------------------------------------
# Öğretmen ekranları (hepsi giriş gerektirir)
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    courses = request.user.courses.annotate(session_count=Count("sessions"))
    active_sessions = AttendanceSession.objects.active().filter(course__teacher=request.user)
    return render(request, "attendance/dashboard.html", {
        "courses": courses,
        "active_sessions": active_sessions,
        "course_form": CourseForm(),
    })


@login_required
@require_POST
def course_create(request):
    form = CourseForm(request.POST)
    if form.is_valid():
        course = form.save(commit=False)
        course.teacher = request.user
        course.save()
        messages.success(request, f"“{course}” dersi eklendi.")
        return redirect("course_detail", pk=course.pk)
    messages.error(request, "Ders eklenemedi, lütfen alanları kontrol edin.")
    return redirect("dashboard")


@login_required
def course_detail(request, pk):
    course = get_object_or_404(Course, pk=pk, teacher=request.user)
    sessions = course.sessions.annotate(record_count=Count("records"))
    return render(request, "attendance/course_detail.html", {
        "course": course,
        "sessions": sessions,
        "start_form": StartSessionForm(),
    })


@login_required
@require_POST
def session_start(request, pk):
    course = get_object_or_404(Course, pk=pk, teacher=request.user)
    form = StartSessionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Geçerli bir süre girin (1-180 dakika).")
        return redirect("course_detail", pk=course.pk)

    # Aynı ders için aynı anda yalnızca bir açık oturum olsun.
    for old in AttendanceSession.objects.active().filter(course=course):
        old.close()

    now = timezone.now()
    session = AttendanceSession.objects.create(
        course=course,
        started_at=now,
        ends_at=now + timedelta(minutes=form.cleaned_data["duration_minutes"]),
    )
    return redirect("session_live", pk=session.pk)


@login_required
def session_live(request, pk):
    session = _get_own_session(request, pk)
    return render(request, "attendance/session_live.html", {
        "session": session,
        "qr_code_b64": _qr_png_base64(_checkin_url(request, session)) if session.is_active else None,
    })


@login_required
@require_POST
def session_refresh_qr(request, pk):
    """Panel bu adresi birkaç saniyede bir çağırır: token yenilenir, yeni QR döner."""
    session = _get_own_session(request, pk)
    if not session.is_active:
        return JsonResponse({"active": False})
    session.rotate_token()
    return JsonResponse({
        "active": True,
        "qr_code_b64": _qr_png_base64(_checkin_url(request, session)),
        "record_count": session.records.count(),
    })


@login_required
@require_POST
def session_close(request, pk):
    session = _get_own_session(request, pk)
    session.close()
    messages.success(request, "Yoklama oturumu kapatıldı.")
    return redirect("session_live", pk=session.pk)


@login_required
def session_export(request, pk):
    session = _get_own_session(request, pk)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Yoklama"
    ws.append(["Ad", "Soyad", "Numara", "Katılım zamanı"])
    for r in session.records.all():
        ws.append([
            _excel_safe(r.first_name),
            _excel_safe(r.last_name),
            r.student_number,
            timezone.localtime(r.created_at).strftime("%d.%m.%Y %H:%M:%S"),
        ])

    filename = f"yoklama_{session.course.code or session.course.pk}_{timezone.localtime(session.started_at):%Y%m%d_%H%M}.xlsx"
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


# ---------------------------------------------------------------------------
# Öğrenci tarafı (giriş gerektirmez)
# ---------------------------------------------------------------------------

def _grant_key(session_id: int) -> str:
    return f"checkin_grant_{session_id}"


def _has_valid_grant(request, session_id: int) -> bool:
    granted_at = request.session.get(_grant_key(session_id))
    return granted_at is not None and time.time() - granted_at < CHECKIN_GRANT_SECONDS


def checkin(request, pk):
    """
    Akış:
    1. Öğrenci QR'ı okutur -> /c/<id>/?t=<token>
    2. Token geçerliyse tarayıcı oturumuna kısa süreli bir "izin" yazılır ve
       token'sız adrese yönlendirilir (token adres çubuğunda kalmaz).
    3. Öğrenci formu bu izin süresi içinde gönderir.
    Böylece QR'ın fotoğrafı başkasına gönderilse bile 15 saniye içinde geçersizleşir.
    """
    session = get_object_or_404(AttendanceSession.objects.select_related("course"), pk=pk)
    context = {"session": session}

    if not session.is_active:
        return render(request, "attendance/checkin_closed.html", context, status=410)

    if request.session.get(f"checked_in_{pk}"):
        return render(request, "attendance/checkin_done.html", context)

    token = request.GET.get("t")
    if token is not None:
        if session.is_token_valid(token):
            request.session[_grant_key(pk)] = time.time()
            return redirect("checkin", pk=pk)
        return render(request, "attendance/checkin_expired.html", context, status=403)

    if not _has_valid_grant(request, pk):
        return render(request, "attendance/checkin_expired.html", context, status=403)

    form = CheckinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.session = session
        record.device_id = form.cleaned_data.get("device_id") or None

        if session.records.filter(student_number=record.student_number).exists():
            form.add_error("student_number", "Bu numarayla bu derste zaten yoklama alınmış.")
        elif record.device_id and session.records.filter(device_id=record.device_id).exists():
            form.add_error(None, "Bu cihazla bu derste zaten yoklama verilmiş.")
        else:
            try:
                # İki istek aynı anda gelirse kontrolü veritabanı kısıtı yapar.
                with transaction.atomic():
                    record.save()
            except IntegrityError:
                form.add_error(None, "Bu yoklama zaten kaydedilmiş.")
            else:
                request.session.pop(_grant_key(pk), None)
                request.session[f"checked_in_{pk}"] = True
                return render(request, "attendance/checkin_done.html", context)

    context["form"] = form
    return render(request, "attendance/checkin.html", context)
