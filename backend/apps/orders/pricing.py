"""
Calcul du frais de livraison. Seule source de vérité côté serveur : le
montant envoyé par le client (`delivery_type`) ne sert qu'à choisir la
formule, jamais à fixer directement le prix payé.

Depuis la prise en charge des partenaires logistiques (spec §31) :
- si une entreprise partenaire active tarife la zone de l'adresse de
  livraison, le « client fee » de sa grille devient le tarif de base affiché
  au client (le partenaire bénéficie alors de la course et en retire son
  `partner_cost`) ;
- sinon on retombe sur la formule distance existante.
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


def best_delivery_partner(address):
    """Meilleure entreprise partenaire active couvrant l'adresse.

    Tri : les partenaires actifs qui tarifent la zone ; on privilégie le
    meilleur score persistant (`score`, mis à jour périodiquement par
    `compute_score`). Une entreprise jamais évaluée (score à 0) est traitée
    comme neutre (100) pour ne pas la pénaliser à son intégration. Renvoie
    `None` si aucune entreprise ne couvre la zone.
    """
    if address is None or address.latitude is None or address.longitude is None:
        return None
    from .models import DeliveryPartner, PartnerZonePricing

    candidates = (
        PartnerZonePricing.objects.select_related("partner", "zone")
        .filter(is_available=True, partner__status=DeliveryPartner.Status.ACTIVE)
    )
    covering = []
    seen = set()
    for zp in candidates:
        zone = zp.zone
        if zone.contains(address.latitude, address.longitude):
            if zp.partner_id in seen:
                continue
            seen.add(zp.partner_id)
            covering.append(zp.partner)
    if not covering:
        return None
    covering.sort(
        key=lambda p: (p.score if p.score > 0 else 100, p.name),
        reverse=True,
    )
    return covering[0]


def zone_pricing_for(partner, address):
    """Tarif zone du partenaire couvrant l'adresse, ou None."""
    if partner is None or address is None or address.latitude is None or address.longitude is None:
        return None
    for zp in partner.zone_pricings.select_related("zone").filter(is_available=True):
        if zp.zone.contains(address.latitude, address.longitude):
            return zp
    return None


def compute_delivery_fee(store, address, delivery_type: str, partner=None) -> Decimal:
    """Frais de livraison en FCFA pour une boutique/adresse/type donnés.

    Si `partner` (ou le meilleur partenaire couvrant la zone) a un tarif
    `client_fee` pour la zone, ce tarif sert de base ; sinon on applique la
    formule distance historique. Le supplément express est toujours ajouté.
    """
    if delivery_type == "pickup":
        return Decimal("0")

    if partner is None:
        partner = best_delivery_partner(address)

    base_fee = None
    if partner is not None:
        zp = zone_pricing_for(partner, address)
        if zp is not None and zp.client_fee and zp.client_fee > 0:
            base_fee = zp.client_fee

    if base_fee is None:
        has_coords = store.latitude is not None and store.longitude is not None and \
            address.latitude is not None and address.longitude is not None

        if has_coords:
            distance_km = haversine_km(
                store.latitude, store.longitude, address.latitude, address.longitude
            )
            base_fee = _round_to_nearest_hundred(BASE_FEE + Decimal(str(distance_km)) * PER_KM_RATE)
        else:
            base_fee = FALLBACK_FEES.get(delivery_type, FALLBACK_FEES["standard"])

    if delivery_type == "express":
        base_fee += EXPRESS_SURCHARGE

    return base_fee


# ---------------------------------------------------------------------------
# Tarification multi-boutiques (spec §4, §8)
# ---------------------------------------------------------------------------

def optimize_route(stores, dest_latitude, dest_longitude):
    """Ordonne les points de collecte en itinéraire simple (glouton).

    La mission profite d'une vraie optimisation d'itinéraire : on construit
    une chaîne gloutonne qui rapproche le livreur du client. Le point le plus
    proche du client est visité en dernier, puis on reboucle sur le point
    restant le plus proche du précédent. Renvoie la liste ordonnée des stores.
    """
    if not stores:
        return []
    visited = []
    remaining = list(stores)
    # Dernier point de l'itinéraire : le plus proche du client.
    last = min(
        remaining,
        key=lambda s: haversine_km(s.latitude, s.longitude, dest_latitude, dest_longitude),
    )
    visited.append(last)
    remaining.remove(last)
    while remaining:
        previous = visited[-1]
        nxt = min(
            remaining,
            key=lambda s: haversine_km(previous.latitude, previous.longitude, s.latitude, s.longitude),
        )
        visited.append(nxt)
        remaining.remove(nxt)
    return visited


def route_distance_km(stores, dest_latitude, dest_longitude):
    """Distance cumulée : points de collecte dans l'ordre puis client."""
    if not stores:
        return Decimal("0")
    total = Decimal("0")
    routed = optimize_route(stores, dest_latitude, dest_longitude)
    prev = routed[0]
    total += Decimal(str(haversine_km(prev.latitude, prev.longitude, dest_latitude, dest_longitude)))
    for store in routed[1:]:
        total += Decimal(str(haversine_km(prev.latitude, prev.longitude, store.latitude, store.longitude)))
        prev = store
    return total


def compute_delivery_fee_multi(stores, address, delivery_type, partner=None, package_count=None,
                               total_weight=None, total_volume=None):
    """Frais de livraison en FCFA pour une commande multi-boutiques.

    Formule (tous les montants proviennent de `DeliveryPricingRule`, table
    configurable par l'administration — jamais de montants codés en dur) :

        base_fee
        + extra_pickup_fee × (nb points de collecte − 1)
        + per_km_fee × distance_de_l_itinéraire
        + weight_per_kg_fee × poids total
        + volume_per_m3_fee × volume total
        + package_fee × nb colis
        + express_surcharge (si express)

    bornée par min_fee / max_fee. Le client paie toujours ce montant ; le
    partenaire se voit attribuer son `partner_cost` (marge Sunu Mall ajoutée
    à part, jamais mélangée aux revenus produits).
    """
    if delivery_type == "pickup":
        return Decimal("0")

    from .models import DeliveryPricingRule

    rule = DeliveryPricingRule.get_or_create_default()

    if partner is None:
        partner = best_delivery_partner(address)

    # Si le partenaire tarife la zone, son client_fee couvre le tarif de base
    # (la distance/poids continuent de s'ajouter selon les règles).
    base_override = None
    if partner is not None:
        zp = zone_pricing_for(partner, address)
        if zp is not None and zp.client_fee and zp.client_fee > 0:
            base_override = zp.client_fee

    coords_stores = [
        s for s in stores
        if s.latitude is not None and s.longitude is not None
    ]
    has_coords = bool(coords_stores) and address is not None and \
        address.latitude is not None and address.longitude is not None

    if has_coords:
        distance_km = route_distance_km(coords_stores, address.latitude, address.longitude)
    else:
        # Sans GPS suffisant : forfait par type basé sur le nombre de points.
        distance_km = Decimal("0")
        fallback = FALLBACK_FEES.get(delivery_type, FALLBACK_FEES["standard"])
        return max(rule.min_fee, fallback * len(stores))

    total = base_override if base_override is not None else rule.base_fee
    total += rule.extra_pickup_fee * (len(stores) - 1)
    total += rule.per_km_fee * distance_km
    if total_weight:
        total += rule.weight_per_kg_fee * total_weight
    if total_volume:
        total += rule.volume_per_m3_fee * total_volume
    if package_count:
        total += rule.package_fee * package_count
    if delivery_type == "express":
        total += rule.express_surcharge

    total = _round_to_nearest_hundred(total)

    if rule.min_fee and total < rule.min_fee:
        total = rule.min_fee
    if rule.max_fee and total > rule.max_fee:
        total = rule.max_fee

    return total