"""Konum hesaplamaları."""

import math

EARTH_RADIUS_M = 6_371_000

# Telefonun bildirdiği konum hassasiyeti bundan kötüyse (ör. kapalı alanda
# yalnızca baz istasyonundan alınan konum) yoklama kabul edilmez.
MAX_ACCEPTED_ACCURACY_M = 200


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    İki koordinat arasındaki kuş uçuşu mesafeyi metre cinsinden verir.
    Dünya'nın küreselliğini hesaba katan Haversine formülü kullanılır;
    düz bir düzlemde Pisagor ile hesaplamak enlem arttıkça hatalı olur.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def is_within_radius(
    center_lat: float, center_lon: float, radius_m: int,
    lat: float, lon: float, accuracy_m: float,
) -> tuple[bool, float]:
    """
    Öğrencinin sınıf yarıçapı içinde olup olmadığını döner.
    GPS'in bildirdiği hata payı (accuracy) kadar tolerans tanınır; aksi halde
    sınıfın içindeki bir öğrenci bile kötü sinyal yüzünden reddedilebilirdi.
    """
    distance = haversine_m(center_lat, center_lon, lat, lon)
    return distance - accuracy_m <= radius_m, distance
