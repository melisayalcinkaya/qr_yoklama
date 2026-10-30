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
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import CheckinForm, CourseForm, CourseSettingsForm, StartSessionForm
from .geo import MAX_ACCEPTED_ACCURACY_M, is_within_radius
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
def course_settings(request, pk):
    course = get_object_or_404(Course, pk=pk, teacher=request.user)
    form = CourseSettingsForm(request.POST or None, instance=course)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ders ayarları kaydedildi.")
        return redirect("course_detail", pk=course.pk)
    return render(request, "attendance/course_settings.html", {"course": course, "form": form})


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
    })


@login_required
@require_GET
def session_records(request, pk):
    """
    Canlı liste için yalnızca yeni kayıtları döner (?after=<son görülen id>).
    Her seferinde tüm listeyi göndermek yerine farkı göndermek ağ trafiğini azaltır.
    """
    session = _get_own_session(request, pk)
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0
    records = session.records.filter(pk__gt=after).order_by("pk")
    return JsonResponse({
        "active": session.is_active,
        "total": session.records.count(),
        "records": [
            {
                "id": r.pk,
                "name": f"{r.first_name} {r.last_name}",
                "number": r.student_number,
                "time": timezone.localtime(r.created_at).strftime("%H:%M:%S"),
                "distance": r.distance_m,
            }
            for r in records
        ],
    })


@login_required
@require_POST
def record_delete(request, pk):
    """Öğretmen hatalı ya da şüpheli bir kaydı listeden çıkarabilir."""
    record = get_object_or_404(
        AttendanceRecord, pk=pk, session__course__teacher=request.user
    )
    record.delete()
    return JsonResponse({"deleted": pk})


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
# İstatistikler
# ---------------------------------------------------------------------------

# Bu oranın altındaki öğrenciler "devamsızlık riski" olarak işaretlenir.
MIN_ATTENDANCE_RATE = 70


def _course_stats(course: Course) -> dict:
    """
    Tek bir veritabanı sorgusuyla öğrenci başına katıldığı oturum sayısını hesaplar.
    Python'da döngüyle saymak yerine işi veritabanına (GROUP BY) yaptırmak,
    kayıt sayısı büyüdükçe çok daha hızlıdır.
    """
    sessions = list(course.sessions.annotate(record_count=Count("records")).order_by("started_at"))
    total_sessions = len(sessions)

    rows = (
        AttendanceRecord.objects.filter(session__course=course)
        .values("student_number")
        .annotate(attended=Count("session", distinct=True), last_seen=Max("created_at"))
    )
    # Öğrencinin en son girdiği adı göster (yazım hatası düzeltilmiş olabilir).
    names = {}
    for number, first, last in (
        AttendanceRecord.objects.filter(session__course=course)
        .order_by("created_at")
        .values_list("student_number", "first_name", "last_name")
    ):
        names[number] = f"{first} {last}"

    students = []
    for row in rows:
        rate = round(100 * row["attended"] / total_sessions) if total_sessions else 0
        students.append({
            "number": row["student_number"],
            "name": names.get(row["student_number"], ""),
            "attended": row["attended"],
            "missed": total_sessions - row["attended"],
            "rate": rate,
            "at_risk": rate < MIN_ATTENDANCE_RATE,
            "last_seen": row["last_seen"],
        })
    students.sort(key=lambda s: (s["rate"], s["name"]))

    max_count = max((s.record_count for s in sessions), default=0)
    average = round(sum(s.record_count for s in sessions) / total_sessions, 1) if total_sessions else 0
    return {
        "sessions": sessions,
        "total_sessions": total_sessions,
        "students": students,
        "at_risk_count": sum(1 for s in students if s["at_risk"]),
        "average_attendance": average,
        "max_count": max_count,
        "min_rate": MIN_ATTENDANCE_RATE,
    }


@login_required
def course_stats(request, pk):
    course = get_object_or_404(Course, pk=pk, teacher=request.user)
    stats = _course_stats(course)
    # Grafik için son 20 oturum; çubuk yüksekliği en kalabalık oturuma göre ölçeklenir.
    chart = [
        {
            "label": timezone.localtime(s.started_at).strftime("%d.%m"),
            "count": s.record_count,
            "height": round(100 * s.record_count / stats["max_count"]) if stats["max_count"] else 0,
        }
        for s in stats["sessions"][-20:]
    ]
    return render(request, "attendance/course_stats.html", {"course": course, "chart": chart, **stats})


@login_required
def course_stats_export(request, pk):
    course = get_object_or_404(Course, pk=pk, teacher=request.user)
    stats = _course_stats(course)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Devam durumu"
    ws.append(["Numara", "Ad Soyad", "Katıldığı", "Kaçırdığı", "Devam oranı (%)", "Risk"])
    for s in stats["students"]:
        ws.append([
            _excel_safe(s["number"]),
            _excel_safe(s["name"]),
            s["attended"],
            s["missed"],
            s["rate"],
            "Evet" if s["at_risk"] else "",
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="devam_durumu_{course.code or course.pk}.xlsx"'
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


def _check_location(course: Course, data: dict) -> tuple[str | None, int | None]:
    """Konum doğrulaması açıksa (hata mesajı, mesafe) döner; sorun yoksa hata None olur."""
    if not course.location_enabled:
        return None, None
    lat, lon, acc = data.get("latitude"), data.get("longitude"), data.get("accuracy")
    if lat is None or lon is None or acc is None:
        return "Bu ders için konum izni gerekiyor. Lütfen tarayıcının konum iznini açın.", None
    if acc > MAX_ACCEPTED_ACCURACY_M:
        return "Konum hassasiyeti çok düşük. Wi-Fi veya GPS'i açıp tekrar deneyin.", None
    inside, distance = is_within_radius(course.latitude, course.longitude, course.radius_m, lat, lon, acc)
    if not inside:
        return f"Sınıfın dışında görünüyorsunuz (yaklaşık {round(distance)} m uzakta).", round(distance)
    return None, round(distance)


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
        location_error, record.distance_m = _check_location(session.course, form.cleaned_data)

        if location_error:
            form.add_error(None, location_error)
        elif session.records.filter(student_number=record.student_number).exists():
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
