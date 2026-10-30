from django.shortcuts import render, redirect

# Create your views here.
from django.http import HttpResponse
from django.utils import timezone
from .models import AttendanceSession, AttendanceRecord
from django.views.decorators.csrf import csrf_exempt
import qrcode
import io
import openpyxl
import base64
from django.http import JsonResponse
import uuid

def generate_qr(request):
    session = AttendanceSession.objects.create(
        expires_at=timezone.now() + timezone.timedelta(minutes=5)
    )
    current_host = request.build_absolute_uri('/')[:-1]
    qr_url = f"{current_host}/attendance/checkin/?session={session.id}&token={session.token}"

    qr_img = qrcode.make(qr_url)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")

def teacher_dashboard(request):
    session = AttendanceSession.objects.filter(is_active=True).order_by("-id").first()

    if not session:
        session = AttendanceSession.objects.create(
            expires_at=timezone.now() + timezone.timedelta(minutes=60)
        )

    current_host = request.build_absolute_uri('/')[:-1]
    qr_url = f"{current_host}/attendance/checkin/?session={session.id}&token={session.token}"

    qr_img = qrcode.make(qr_url)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_code_b64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, "attendance/teacher_dashboard.html", {
        "session": session,
        "qr_code_b64": qr_code_b64,
        "qr_url": qr_url
    })


def refresh_qr(request):
    session = AttendanceSession.objects.filter(is_active=True).order_by("-id").first()

    if not session:
        return JsonResponse({"error": "No active session"}, status=400)

    session.token = uuid.uuid4().hex
    session.token_expires_at = timezone.now() + timezone.timedelta(minutes=2)  # TOKEN 2 DAKİKA GEÇERLİ
    session.save()

    current_host = request.build_absolute_uri('/')[:-1]
    qr_url = f"{current_host}/attendance/checkin/?session={session.id}&token={session.token}"

    qr_img = qrcode.make(qr_url)
    buffer = io.BytesIO()
    qr_img.save(buffer, "PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    return JsonResponse({
        "session_id": session.id,
        "qr_code_b64": qr_b64
    })


@csrf_exempt
def checkin(request):
    session_id = request.GET.get("session")
    token = request.GET.get("token")

    try:
        session = AttendanceSession.objects.get(id=session_id, is_active=True)
    except AttendanceSession.DoesNotExist:
        return HttpResponse("Geçersiz veya süresi dolmuş QR kodu.")

    if token != session.token and timezone.now() > session.token_expires_at:
        return HttpResponse("QR kodun süresi dolmuş.")

    if request.method == "POST":
        student_number = request.POST.get("student_number")
        student_name = request.POST.get("student_name")
        student_surname = request.POST.get("student_surname")
        device_id = request.POST.get("device_id")

        if AttendanceRecord.objects.filter(session=session, student_number=student_number).exists():
            return HttpResponse("Bu öğrenci zaten yoklama almış.")
        
        if device_id and AttendanceRecord.objects.filter(session=session, device_id=device_id).exists():
            return HttpResponse("Bu cihaz bu yoklama için zaten kullanıldı.")
        
        AttendanceRecord.objects.create(
            session=session,
            student_number=student_number,
            student_name=student_name,
            student_surname=student_surname,
            device_id=device_id
        )
        return HttpResponse("✅ Yoklamanız başarıyla alındı!")

    return render(request, "attendance/checkin.html", {"session": session})

def export_attendance(request, session_id):
    try:
        session = AttendanceSession.objects.get(id=session_id)
    except AttendanceSession.DoesNotExist:
        return HttpResponse("Geçersiz yoklama oturumu.")

    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Yoklama"

    
    ws.append(["Ad", "Soyad", "Numara", "Tarih"])

    records = AttendanceRecord.objects.filter(session=session)
    for r in records:
        ws.append([r.student_name, r.student_surname, r.student_number, r.timestamp.strftime("%Y-%m-%d %H:%M:%S")])

    
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response['Content-Disposition'] = f'attachment; filename=attendance_session_{session_id}.xlsx'

    wb.save(response)
    return response