"""
Outils géographiques purs (aucune dépendance) utilisés par le suivi
GPS temps réel : distance de Haversine, appartenance à une zone de
livraison (point-in-polygon) et estimation du temps restant (ETA).

Toutes les fonctions sont pures et facilement testables unitairement.
"""
from math import asin, cos, radians, sin, sqrt

# Rayon moyen de la Terre en kilomètres.
EARTH_RADIUS_KM = 6371.0

# Vitesse moyenne retenue pour l'ETA en euclidien urbain (km/h).
# Modeste volontairement : la distance est "à vol d'oiseau", la réalité
# routière est presque toujours plus longue (rues, feux, embouteillages).
DEFAULT_SPEED_KMH = 30


def haversine_km(lat1, lng1, lat2, lng2):
    """Distance en kilomètres entre deux points (loi de Haversine)."""
    lat1, lng1, lat2, lng2 = (float(v) for v in (lat1, lng1, lat2, lng2))
    p1, p2 = radians(lat1), radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    a = sin(delta_lat / 2) ** 2 + cos(p1) * cos(p2) * sin(delta_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def point_in_polygon(lat, lng, polygon):
    """Ray casting standard : le point appartient-il au polygone ?

    ``polygon`` est une liste de coordonnées [lat, lng] (ou (lng, lat),
    peu importe tant que c'est homogène). Un point exactement sur une
    frontière est considéré dedans.
    """
    if not polygon:
        return False
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-9) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def compute_eta_seconds(origin_lat, origin_lng, dest_lat, dest_lng, speed_kmh=DEFAULT_SPEED_KMH):
    """Temps estimé de trajet en secondes, ou None si une coordonnée manque."""
    for value in (origin_lat, origin_lng, dest_lat, dest_lng):
        if value is None:
            return None
    try:
        origin_lat, origin_lng = float(origin_lat), float(origin_lng)
        dest_lat, dest_lng = float(dest_lat), float(dest_lng)
    except (TypeError, ValueError):
        return None
    distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
    return int(round(distance_km / speed_kmh * 3600))