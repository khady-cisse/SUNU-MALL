"""
Recherche globale SUNU MALL.
Recherche textuelle transversale sur les principales entités de la plateforme.
Reconnaît automatiquement les références (CMD-, PLT-, PAY-, KYC-, DRV-, INC-).
"""
import re

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdmin


# Patterns de reconnaissance d'identifiants
REFERENCE_PATTERNS = {
    "orders": re.compile(r"^CMD[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
    "complaints": re.compile(r"^PLT[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
    "payments": re.compile(r"^PAY[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
    "kyc": re.compile(r"^KYC[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
    "drivers": re.compile(r"^DRV[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
    "incidents": re.compile(r"^INC[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
    "tickets": re.compile(r"^(?:TKT|TCK)[- ]?\d{8}[- ]?\d+$", re.IGNORECASE),
}


def _user_results(query):
    from apps.users.models import User
    users = User.objects.filter(
        Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(email__icontains=query)
        | Q(phone__icontains=query)
    )[:10]
    return [
        {
            "type": "users",
            "label": f"{u.first_name} {u.last_name}".strip() or u.email,
            "subtitle": u.email,
            "to": f"/admin-users?highlight={u.id}",
        }
        for u in users
    ]


def _store_results(query):
    from apps.catalog.models import Store
    stores = Store.objects.filter(
        Q(name__icontains=query) | Q(owner__email__icontains=query)
    ).select_related("owner")[:10]
    return [
        {
            "type": "stores",
            "label": s.name,
            "subtitle": f"{s.owner.first_name} {s.owner.last_name}".strip(),
            "to": f"/admin-shops?highlight={s.id}",
        }
        for s in stores
    ]


def _product_results(query):
    from apps.catalog.models import Product
    products = Product.objects.filter(
        Q(name__icontains=query) | Q(brand__icontains=query)
    ).select_related("store")[:10]
    return [
        {
            "type": "products",
            "label": p.name,
            "subtitle": f"{p.store.name} — {p.base_price} FCFA",
            "to": f"/admin-products?highlight={p.id}",
        }
        for p in products
    ]


def _order_results(query):
    from apps.orders.models import Order
    orders = Order.objects.filter(
        Q(id__icontains=query)
        | Q(customer__first_name__icontains=query)
        | Q(customer__last_name__icontains=query)
        | Q(customer__email__icontains=query)
    ).select_related("customer", "store")[:10]
    return [
        {
            "type": "orders",
            "label": f"Commande — {o.customer.first_name} {o.customer.last_name}",
            "subtitle": f"{o.store.name} — {o.total_amount} FCFA",
            "to": f"/admin-order-detail?order={o.id}",
        }
        for o in orders
    ]


def _payment_results(query):
    from apps.payments.models import Payment
    payments = Payment.objects.filter(
        Q(provider_ref__icontains=query)
        | Q(id__icontains=query)
    ).select_related("order")[:10]
    return [
        {
            "type": "payments",
            "label": f"Paiement {p.get_method_display()} — {p.amount} FCFA",
            "subtitle": f"Statut : {p.status}",
            "to": f"/admin-payments",
        }
        for p in payments
    ]


def _complaint_results(query):
    from apps.complaints.models import Complaint
    complaints = Complaint.objects.filter(
        Q(reference__icontains=query)
        | Q(complainant__first_name__icontains=query)
        | Q(complainant__last_name__icontains=query)
        | Q(description__icontains=query)
    ).select_related("complainant")[:10]
    return [
        {
            "type": "complaints",
            "label": c.reference,
            "subtitle": f"{c.get_category_display()} — {c.get_status_display()}",
            "to": f"/admin-complaints?highlight={c.id}",
        }
        for c in complaints
    ]


def _driver_results(query):
    from apps.orders.models import Driver
    drivers = Driver.objects.filter(
        Q(user__first_name__icontains=query)
        | Q(user__last_name__icontains=query)
        | Q(user__email__icontains=query)
        | Q(user__phone__icontains=query)
    ).select_related("user")[:10]
    return [
        {
            "type": "drivers",
            "label": f"{d.user.first_name} {d.user.last_name}".strip(),
            "subtitle": d.user.email,
            "to": f"/admin-drivers?highlight={d.id}",
        }
        for d in drivers
    ]


SEARCH_DISPATCHERS = [
    _user_results,
    _store_results,
    _product_results,
    _order_results,
    _payment_results,
    _complaint_results,
    _driver_results,
]


class GlobalSearchView(APIView):
    """Recherche globale multi-entités."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response({})

        # Vérifier si c'est une référence exacte
        normalized = query.replace(" ", "").upper()
        for entity_type, pattern in REFERENCE_PATTERNS.items():
            if pattern.match(normalized):
                return Response(self._resolve_reference(entity_type, normalized))

        # Recherche textuelle sur toutes les entités
        results = {}
        for dispatcher in SEARCH_DISPATCHERS:
            try:
                items = dispatcher(query)
                if items:
                    results[items[0]["type"]] = items
            except Exception:
                continue
        return Response(results)

    def _resolve_reference(self, entity_type, ref):
        """Résout une référence exacte et redirige directement."""
        if entity_type == "orders":
            from apps.orders.models import Order
            try:
                order = Order.objects.get(id__icontains=ref.replace("CMD", ""))
                return {"orders": [{"type": "orders", "label": f"Commande {order.id}", "subtitle": f"{order.total_amount} FCFA", "to": f"/admin-order-detail?order={order.id}"}]}
            except Order.DoesNotExist:
                pass
        elif entity_type == "complaints":
            from apps.complaints.models import Complaint
            try:
                complaint = Complaint.objects.get(reference__icontains=ref.replace("PLT", ""))
                return {"complaints": [{"type": "complaints", "label": complaint.reference, "subtitle": complaint.get_status_display(), "to": f"/admin-complaints?highlight={complaint.id}"}]}
            except Complaint.DoesNotExist:
                pass
        return {}


class AdvancedSearchView(APIView):
    """Recherche avancée : entités + filtres (statut, boutique, dates).

    Corps attendu (JSON) :
        {
          "query": "texte optionnel",
          "entities": ["users", "orders", ...],    (vide = toutes)
          "status": "active|pending|...",
          "date_from": "YYYY-MM-DD",
          "date_to": "YYYY-MM-DD",
          "limit": 20
        }
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request):
        body = request.data or {}
        query = str(body.get("query", "")).strip()
        entities = body.get("entities") or []
        status = str(body.get("status", "")).strip()
        date_from = str(body.get("date_from", "")).strip()
        date_to = str(body.get("date_to", "")).strip()
        try:
            limit = min(int(body.get("limit", 20)), 100)
        except (TypeError, ValueError):
            limit = 20

        wanted = {e for e in entities if e in {"users", "stores", "products", "orders", "payments", "deliveries", "complaints", "drivers"}}
        use_all = not wanted
        results = {}

        def _scope_date(qs):
            if date_from:
                qs = qs.filter(created_at__date__gte=date_from)
            if date_to:
                qs = qs.filter(created_at__date__lte=date_to)
            return qs

        if use_all or "users" in wanted:
            from apps.users.models import User
            qs = User.objects.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )
            if status:
                qs = qs.filter(is_active=(status == "active"))
            items = [
                {"type": "users", "label": f"{u.first_name} {u.last_name}".strip() or u.email,
                 "subtitle": u.email, "meta": {"status": "actif" if u.is_active else "inactif"},
                 "to": f"/admin-users/{u.id}"}
                for u in _scope_date(qs)[:limit]
            ]
            if items:
                results["users"] = items

        if use_all or "stores" in wanted:
            from apps.catalog.models import Store
            qs = Store.objects.filter(Q(name__icontains=query) | Q(owner__email__icontains=query)).select_related("owner")
            if status:
                qs = qs.filter(status=status)
            items = [
                {"type": "stores", "label": s.name, "subtitle": s.owner.email,
                 "meta": {"status": s.get_status_display()}, "to": f"/admin-shops?highlight={s.id}"}
                for s in _scope_date(qs)[:limit]
            ]
            if items:
                results["stores"] = items

        if use_all or "products" in wanted:
            from apps.catalog.models import Product
            qs = Product.objects.filter(
                Q(name__icontains=query)
                | Q(brand__name__icontains=query)
            ).select_related("store")
            if status:
                qs = qs.filter(status=status)
            items = [
                {"type": "products", "label": p.name, "subtitle": f"{p.store.name} — {p.base_price} FCFA",
                 "meta": {"status": p.get_status_display()}, "to": f"/admin-products?highlight={p.id}"}
                for p in _scope_date(qs)[:limit]
            ]
            if items:
                results["products"] = items

        if use_all or "orders" in wanted:
            from apps.orders.models import Order
            qs = Order.objects.filter(
                Q(id__icontains=query)
                | Q(customer__first_name__icontains=query)
                | Q(customer__last_name__icontains=query)
                | Q(customer__email__icontains=query)
            ).select_related("customer", "store")
            if status:
                qs = qs.filter(status=status)
            items = [
                {"type": "orders", "label": f"Commande — {o.customer.first_name} {o.customer.last_name}",
                 "subtitle": f"{o.store.name} — {o.total_amount} FCFA",
                 "meta": {"status": o.get_status_display()}, "to": f"/admin-order-detail?order={o.id}"}
                for o in _scope_date(qs)[:limit]
            ]
            if items:
                results["orders"] = items

        if use_all or "payments" in wanted:
            from apps.payments.models import Payment
            qs = Payment.objects.filter(Q(provider_ref__icontains=query) | Q(id__icontains=query)).select_related("order")
            if status:
                qs = qs.filter(status=status)
            items = [
                {"type": "payments", "label": f"Paiement {p.method} — {p.amount} FCFA",
                 "subtitle": f"Statut : {p.get_status_display()}",
                 "meta": {"method": p.method, "status": p.get_status_display()}, "to": "/admin-payments"}
                for p in _scope_date(qs)[:limit]
            ]
            if items:
                results["payments"] = items

        if use_all or "deliveries" in wanted:
            from apps.orders.models import Delivery
            qs = Delivery.objects.filter(order__id__icontains=query).select_related("order", "driver__user")
            if status:
                qs = qs.filter(status=status)
            items = [
                {"type": "deliveries", "label": f"Livraison {str(d.order_id)[:8]}",
                 "subtitle": d.driver.user.email if d.driver_id else "Aucun livreur",
                 "meta": {"status": d.get_status_display()}, "to": "/admin-deliveries"}
                for d in _scope_date(qs)[:limit]
            ]
            if items:
                results["deliveries"] = items

        if use_all or "complaints" in wanted:
            from apps.complaints.models import Complaint
            qs = Complaint.objects.filter(
                Q(reference__icontains=query)
                | Q(complainant__first_name__icontains=query)
                | Q(complainant__last_name__icontains=query)
                | Q(description__icontains=query)
            ).select_related("complainant")
            if status:
                qs = qs.filter(status=status)
            items = [
                {"type": "complaints", "label": c.reference,
                 "subtitle": f"{c.get_category_display()} — {c.get_status_display()}",
                 "meta": {"status": c.get_status_display()}, "to": f"/admin-complaints?highlight={c.id}"}
                for c in _scope_date(qs)[:limit]
            ]
            if items:
                results["complaints"] = items

        if use_all or "drivers" in wanted:
            from apps.orders.models import Driver
            qs = Driver.objects.filter(
                Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__email__icontains=query)
                | Q(user__phone__icontains=query)
            ).select_related("user")
            if status:
                qs = qs.filter(availability_status=status)
            items = [
                {"type": "drivers", "label": f"{d.user.first_name} {d.user.last_name}".strip(),
                 "subtitle": d.user.email,
                 "meta": {"status": d.get_availability_status_display()}, "to": f"/admin-drivers?highlight={d.id}"}
                for d in _scope_date(qs)[:limit]
            ]
            if items:
                results["drivers"] = items

        return Response(results)
