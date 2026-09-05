"""
Calcul du frais de livraison. Seule source de vérité côté serveur : le
montant envoyé par le client (`delivery_type`) ne sert qu'à choisir la
formule, jamais à fixer directement le prix payé.
"""
from decimal import Decimal, ROUND_HALF_UP

from .geoutils import haversine_km

BASE_FEE = Decimal("500")
PER_KM_RATE = Decimal("150")
EXPRESS_SURCHARGE = Decimal("800")

# Utilisé quand la boutique ou l'adresse n'a pas encore de coordonnées GPS
# (ex. boutique créée avant l'ajout de ce champ) : on retombe sur les
# anciens forfaits fixes plutôt que de planter le checkout.
FALLBACK_FEES = {
    "pickup": Decimal("0"),
    "standard": Decimal("1000"),
    "express": Decimal("2000"),
}


def _round_to_nearest_hundred(value: Decimal) -> Decimal:
    return (value / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 100


def compute_delivery_fee(store, address, delivery_type: str) -> Decimal:
    """Frais de livraison en FCFA pour une boutique/adresse/type donnés."""
    if delivery_type == "pickup":
        return Decimal("0")

    has_coords = store.latitude is not None and store.longitude is not None and \
        address.latitude is not None and address.longitude is not None

    if has_coords:
        distance_km = haversine_km(store.latitude, store.longitude, address.latitude, address.longitude)
        fee = _round_to_nearest_hundred(BASE_FEE + Decimal(str(distance_km)) * PER_KM_RATE)
    else:
        fee = FALLBACK_FEES.get(delivery_type, FALLBACK_FEES["standard"])

    if delivery_type == "express":
        fee += EXPRESS_SURCHARGE

    return fee
