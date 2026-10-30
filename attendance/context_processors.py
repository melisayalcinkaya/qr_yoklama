from django.conf import settings


def demo_mode(request):
    """Şablonlarda {{ demo_mode }} değişkenini kullanılabilir yapar."""
    return {"demo_mode": getattr(settings, "DEMO_MODE", False)}
