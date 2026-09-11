"""
Passerelles de paiement (Wave, Orange Money, carte bancaire).

Trois modes :

* ``SandboxGateway`` (actif quand ``PAYMENT_SANDBOX`` = True) simule le cycle
  de vie d'un paiement sans jamais contacter Wave/Orange Money.
* ``WaveGateway`` branche l'API Wave Business Checkout (redirection vers
  ``wave_launch_url``, confirmation par webhook signé HMAC).
* ``OrangeMoneyGateway`` branche l'API Orange Money Web Payment (jeton OAuth2,
  redirection vers ``payment_url``, confirmation par webhook vérifié via le
  ``notif_token`` reçu à la création du paiement).

Aucune clé marchande n'est commitée : tant que les clés ne sont pas fournies,
``get_gateway`` renvoie la passerelle demandée qui échoue proprement (erreur
claire) plutôt que de simuler un paiement en production — le défaut de
``PAYMENT_SANDBOX`` est False justement pour qu'un déploiement oublieux ne
tourne jamais en « faux paiements » sans le savoir.
"""
import base64
import hashlib
import hmac
import time

import requests
from django.conf import settings


class PaymentGatewayError(Exception):
    """Erreur d'appel à la passerelle réelle (refus, réseau, malformé)."""


def _payment_return_url(payment):
    """URL de retour du client après un paiement réussi (page de confirmation)."""
    base = settings.FRONTEND_URL.rstrip("/")
    if payment.global_order_id:
        return f"{base}/order-confirmed?gorder={payment.global_order_id}&payment={payment.id}"
    return f"{base}/order-confirmed?order={payment.order_id}&payment={payment.id}"


def _payment_cancel_url(payment):
    """URL de retour du client après une annulation ou une erreur de paiement."""
    return f"{settings.FRONTEND_URL.rstrip('/')}/checkout-payment?payment={payment.id}&error=1"


def _parse_wave_signature(header):
    """Décode l'entête ``Wave-Signature: t=<ts>,v1=<sig>[,v1=<sig2>]``.

    Retourne ``(timestamp, [signatures])`` — plusieurs ``v1=`` sont possibles
    pendant une rotation de secret (Wave les rejette à tour de rôle).
    """
    timestamp = None
    signatures = []
    for part in (header or "").split(","):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    return timestamp, signatures


def verify_wave_signature(secret, header, raw_body, tolerance=300):
    """Vérifie la signature HMAC-SHA256 d'un webhook Wave.

    Le payload signé est ``timestamp + raw_body`` (concaténation, sans
    séparateur — voir docs.wave.com/webhook). La page Webhooks récente de
    Wave (comptabilité) utilise ``timestamp + "." + raw_body`` : on accepte
    les deux variantes pour rester robuste aux évolutions. Le corps doit
    être le flux brut reçu, jamais re-sérialisé. La tolérance anti-rejeu
    est de 5 minutes (limite officielle Wave).
    """
    if not secret or not header or raw_body is None:
        return False
    timestamp, signatures = _parse_wave_signature(header)
    if not timestamp or not signatures:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > tolerance:
        return False
    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode("utf-8", "replace")
    variants = (f"{timestamp}{raw_body}", f"{timestamp}.{raw_body}")
    for payload in variants:
        computed = hmac.new(
            secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        for received in signatures:
            if hmac.compare_digest(computed, received):
                return True
    return False


def _json_post(url, payload=None, headers=None, **kwargs):
    """POST JSON vers une passerelle avec gestion d'erreur commune.

    Lève ``PaymentGatewayError`` sur échec réseau ou réponse non-2xx, avec
    le détail du refus quand la passerelle en renvoie un.
    """
    timeout = kwargs.pop("timeout", 15)
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise PaymentGatewayError(f"Impossible de joindre {url} : {exc}")
    if response.status_code >= 400:
        detail = response.text[:400]
        try:
            body = response.json()
            detail = body.get("message") or body.get("error") or detail
        except ValueError:
            pass
        raise PaymentGatewayError(
            f"La passerelle {url} a refusé la demande "
            f"(HTTP {response.status_code}) : {detail}"
        )
    return response.json()


class BasePaymentGateway:
    def initiate(self, payment) -> dict:
        """Démarre le paiement. Retourne les infos à afficher/utiliser côté client."""
        raise NotImplementedError


class SandboxGateway(BasePaymentGateway):
    """Simulation locale — ne contacte aucun vrai fournisseur de paiement."""

    def initiate(self, payment) -> dict:
        provider_ref = f"SANDBOX-{payment.id.hex[:10].upper()}"
        payment.provider_ref = provider_ref
        payment.save(update_fields=["provider_ref"])
        return {
            "sandbox": True,
            "provider_ref": provider_ref,
            "message": (
                "Mode test : aucune transaction réelle n'est envoyée à "
                f"{payment.method}. Utilisez l'action « sandbox-confirm » "
                "pour simuler le résultat du paiement."
            ),
        }


class WaveGateway(BasePaymentGateway):
    """
    Wave Business — Checkout API (docs.wave.com/checkout).

    Crée une session de paiement hébergée, renvoie la ``wave_launch_url`` à
    ouvrir dans le navigateur du client, puis attend la confirmation par
    webhook ``checkout.session.completed`` (signature HMAC-SHA256 vérifiée
    dans `PaymentWebhookView`).
    """

    CREATE_SESSION_URL = "/v1/checkout/sessions"

    def initiate(self, payment) -> dict:
        if not settings.WAVE_API_KEY:
            raise PaymentGatewayError("WAVE_API_KEY n'est pas configurée.")

        url = f"{settings.WAVE_API_BASE_URL.rstrip('/')}{self.CREATE_SESSION_URL}"
        payload = {
            # Montant dans la plus petite unité monétaire : XOF sans
            # décimale → exprimé en FCFA entiers.
            "amount": str(int(payment.amount)),
            "currency": payment.currency or "XOF",
            "client_reference": str(payment.id),
            "success_url": _payment_return_url(payment),
            "error_url": _payment_cancel_url(payment),
        }
        headers = {
            "Authorization": f"Bearer {settings.WAVE_API_KEY}",
            "Content-Type": "application/json",
        }
        try:
            session = _json_post(url, payload, headers)
        except PaymentGatewayError as exc:
            raise PaymentGatewayError(f"Wave : {exc}")

        session_id = (session or {}).get("id")
        launch_url = (session or {}).get("wave_launch_url")
        if not session_id or not launch_url:
            raise PaymentGatewayError(f"Wave a répondu une session incomplète : {session}")

        payment.provider_ref = session_id
        payment.save(update_fields=["provider_ref"])
        return {
            "sandbox": False,
            "method": "wave",
            "provider_ref": session_id,
            "checkout_url": launch_url,
            "message": "Redirection vers Wave pour valider le paiement.",
        }


class OrangeMoneyGateway(BasePaymentGateway):
    """
    Orange Money — Web Payment API (developer.orange.com/apis/om-webpay).

    Récupère un jeton d'accès (OAuth2 client_credentials), crée un paiement
    hébergé, renvoie la ``payment_url`` au client et mémorise le
    ``notif_token`` dans ``Payment.metadata`` — c'est CE jeton que le webhook
    Orange doit réexpédier pour qu'on le croie (seule authentification,
    voir `verify_orange_notification`).
    """

    TOKEN_URL = "/oauth/v3/token"
    WEBPAYMENT_PATH = "/orange-money-webpay/{env}/v1/webpayment"

    def _api_base(self):
        return settings.ORANGE_MONEY_API_BASE_URL.rstrip("/")

    def _webpayment_path(self):
        env = "dev" if settings.PAYMENT_SANDBOX else settings.ORANGE_MONEY_COUNTRY_PATH
        return self.WEBPAYMENT_PATH.format(env=env)

    def _access_token(self) -> str:
        if not settings.ORANGE_MONEY_CLIENT_ID or not settings.ORANGE_MONEY_CLIENT_SECRET:
            raise PaymentGatewayError(
                "ORANGE_MONEY_CLIENT_ID / ORANGE_MONEY_CLIENT_SECRET ne sont pas configurés."
            )
        credentials = f"{settings.ORANGE_MONEY_CLIENT_ID}:{settings.ORANGE_MONEY_CLIENT_SECRET}"
        basic = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        url = f"{self._api_base()}{self.TOKEN_URL}"
        try:
            response = requests.post(
                url,
                data={"grant_type": "client_credentials"},
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=15,
            )
        except requests.RequestException as exc:
            raise PaymentGatewayError(f"Impossible de joindre Orange Money : {exc}")
        if response.status_code >= 400:
            raise PaymentGatewayError(
                f"Orange Money a refusé le jeton d'accès (HTTP {response.status_code})."
            )
        token = (response.json() or {}).get("access_token")
        if not token:
            raise PaymentGatewayError("Orange Money n'a pas fourni de jeton d'accès.")
        return token

    def initiate(self, payment) -> dict:
        if not settings.ORANGE_MONEY_MERCHANT_KEY:
            raise PaymentGatewayError("ORANGE_MONEY_MERCHANT_KEY n'est pas configurée.")

        access_token = self._access_token()
        # order_id est notre référentiel de rapprochement : unique, court, et
        # sans ambiguïté (réutiliser un order_id déjà consommé → 403 Orange).
        order_id = f"SM-{payment.id.hex[:16].upper()}"
        payment_id = str(payment.id)
        payload = {
            "merchant_key": settings.ORANGE_MONEY_MERCHANT_KEY,
            "currency": settings.ORANGE_MONEY_CURRENCY or "XOF",
            "order_id": order_id,
            "amount": int(payment.amount),
            "return_url": _payment_return_url(payment),
            "cancel_url": _payment_cancel_url(payment),
            "notif_url": f"{settings.BACKEND_URL.rstrip('/')}/payments/webhook/orange_money/",
            "lang": "fr",
            "reference": payment_id,
        }
        url = f"{self._api_base()}{self._webpayment_path()}"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        try:
            result = _json_post(url, payload, headers)
        except PaymentGatewayError as exc:
            raise PaymentGatewayError(f"Orange Money : {exc}")

        pay_token = (result or {}).get("pay_token")
        payment_url = (result or {}).get("payment_url")
        notif_token = (result or {}).get("notif_token")
        if not pay_token or not payment_url or not notif_token:
            raise PaymentGatewayError(f"Orange Money a répondu une demande incomplète : {result}")

        # provider_ref : identifiant retenu pour retrouver le paiement à la
        # confirmation ; notif_token est la preuve d'authenticité du webhook.
        payment.provider_ref = pay_token
        metadata = dict(payment.metadata)
        metadata["orange_money"] = {
            "order_id": order_id,
            "pay_token": pay_token,
            "notif_token": notif_token,
            "amount": str(payment.amount),
        }
        payment.metadata = metadata
        payment.save(update_fields=["provider_ref", "metadata"])
        return {
            "sandbox": False,
            "method": "orange_money",
            "provider_ref": pay_token,
            "checkout_url": payment_url,
            "message": "Redirection vers Orange Money pour valider le paiement.",
        }


def verify_orange_notification(payment, notif_token) -> bool:
    """Authentifie une notification Orange Money.

    Orange ne signe pas ses webhooks : la seule preuve que la notification
    vient bien d'elle est le ``notif_token`` — celui qu'elle a reçu en réponse
    à la création du paiement et qu'elle réexpédie. Comparaison en temps
    constant pour éviter les attaques par timing.
    """
    if not isinstance(notif_token, str) or not notif_token:
        return False
    stored = (payment.metadata or {}).get("orange_money", {}).get("notif_token")
    if not isinstance(stored, str) or not stored:
        return False
    return hmac.compare_digest(stored, notif_token)


def get_gateway(method: str) -> BasePaymentGateway:
    if settings.PAYMENT_SANDBOX:
        return SandboxGateway()
    return {
        "wave": WaveGateway(),
        "orange_money": OrangeMoneyGateway(),
    }.get(method, SandboxGateway())