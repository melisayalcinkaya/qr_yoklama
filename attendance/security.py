"""Güvenlikle ilgili yardımcılar."""

from django.conf import settings


def get_client_ip(request) -> str | None:
    """
    İsteği gönderen kişinin gerçek IP adresini bulur.

    Uygulama Render gibi bir platformda bir proxy'nin (yük dengeleyici) arkasında
    çalışır; bu durumda REMOTE_ADDR her zaman proxy'nin adresidir. Gerçek adres
    X-Forwarded-For başlığındadır: "istemci, proxy1, proxy2" şeklinde.

    Dikkat: Bu başlığın SOL tarafını istemci istediği gibi yazabilir (sahte IP).
    Bu yüzden güvendiğimiz proxy sayısı kadar SAĞDAN sayarak alırız; o değeri
    kendi altyapımız eklemiştir ve taklit edilemez.
    """
    proxy_count = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if proxy_count and forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= proxy_count:
            return parts[-proxy_count]
    return request.META.get("REMOTE_ADDR")
