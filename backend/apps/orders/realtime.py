"""
Diffusion temps réel des événements de livraison via Redis Pub/Sub.

Chaque livraison a son canal `delivery_events:<delivery_id>`. Le livreur
publie ses positions et changements de statut ; le client (ou le commerçant),
connecté en Server-Sent Events (voir `DeliveryEventStreamView`), reçoit ces
événements dans la seconde.

Le service est dégradable : si Redis est injoignable, toutes les fonctions
font no-op / renvoient None au lieu de faire planter la requête. Le frontend
conserve son polling de secours (10 s) en cas de coupure du flux poussé.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def delivery_channel(delivery_id):
    """Nom du canal Redis portant les événements d'une livraison."""
    return f"delivery_events:{delivery_id}"


def get_redis():
    """Client Redis (vénérer le settings pour un seul point de config).

    Renvoie None si Redis est indisponible : l'appelant doit savoir se
    passer du temps réel (baisse de régime, pas de crash).
    """
    try:
        from redis import Redis
        return Redis.from_url(settings.REDIS_URL)
    except Exception:  # pragma: no cover - dépend de l'environnement
        logger.warning("Redis injoignable : diffusion temps réel désactivée.", exc_info=True)
        return None


def publish_delivery_event(delivery_id, event_type, payload):
    """Publie un événement JSON sur le canal de la livraison.

    « position » : mise à jour GPS du livreur.
    « status »  : changement de statut de la livraison.
    « assigned» : un livreur vient d'être affecté.
    Le champ `event` porte `event_type` ; `payload` contient le contenu.
    """
    _client = get_redis()
    if _client is None:
        return
    try:
        event = {"event": event_type, "delivery_id": str(delivery_id), **payload}
        _client.publish(delivery_channel(delivery_id), json.dumps(event, default=str))
    except Exception:
        logger.warning("Impossible de publier l'événement de livraison %s.", delivery_id, exc_info=True)


def subscribe_delivery_events(delivery_id):
    """Retourne la paire (client_redis, pubsub) abonnée au canal. (None, None) si Redis est coupé."""
    _client = get_redis()
    if _client is None:
        return None, None
    try:
        pubsub = _client.pubsub()
        pubsub.subscribe(delivery_channel(delivery_id))
        return _client, pubsub
    except Exception:
        logger.warning("Abonnement au flux de livraison %s impossible.", delivery_id, exc_info=True)
        return None, None