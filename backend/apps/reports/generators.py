"""
Génération des rapports administrateur (CSV / PDF sans dépendance).

Chaque rapport est décrit par un générateur de sections :
    sections = [{"heading", "kpis": [(libellé, valeur), ...],
                 "table": {"columns": [...], "rows": [[...], ...]}}]
"""
import csv
import io

from django.db.models import Count, Sum, Q
from django.utils import timezone


def _money(value):
    """Formate un montant FCFA sans virgules flottantes gênantes."""
    try:
        return f"{value:,.0f}".replace(",", " ") + " FCFA"
    except (TypeError, ValueError):
        return "0 FCFA"


def _count_breakdown(model, field="status"):
    """Compte les occurrences d'un modèle par valeur du champ."""
    return {row[field]: row["total"] for row in model.objects.values(field).annotate(total=Count("id"))}


def _recent(qs, columns, limit=20):
    """Extrait les `limit` premières lignes d'un queryset avec les extracteurs."""
    return [
        [col(row) for col in columns]
        for row in qs[:limit]
    ]


# ---------------------------------------------------------------- global
def global_report():
    from apps.users.models import User
    from apps.catalog.models import Store, Product
    from apps.orders.models import Order, Delivery
    from apps.payments.models import Payment
    from apps.complaints.models import Complaint

    revenue = Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(total=Sum("amount"))["total"] or 0
    sections = [
        {
            "heading": "Vue d'ensemble de la plateforme",
            "kpis": [
                ("Utilisateurs", User.objects.count()),
                ("Boutiques", Store.objects.count()),
                ("Produits", Product.objects.count()),
                ("Commandes", Order.objects.count()),
                ("Livraisons", Delivery.objects.count()),
                ("Plaintes", Complaint.objects.count()),
                ("Paiements réussis", revenue and _money(revenue) or "0 FCFA"),
            ],
            "table": {
                "columns": ["Commande", "Client", "Boutique", "Montant", "Statut", "Créée le"],
                "rows": _recent(
                    Order.objects.select_related("customer", "store"),
                    [lambda o: str(o.id)[:8], lambda o: o.customer.email, lambda o: o.store.name,
                     lambda o: _money(o.total_amount), lambda o: o.get_status_display(),
                     lambda o: o.created_at.strftime("%d/%m/%Y %H:%M")],
                ),
            },
        }
    ]
    return {
        "title": "Rapport global",
        "sections": sections,
    }


# ---------------------------------------------------------------- finance
def finance_report():
    from apps.payments.models import Payment, Refund
    from apps.commissions.models import CommissionTransaction, Payout

    revenue = Payment.objects.filter(status=Payment.Status.SUCCESS).aggregate(total=Sum("amount"))["total"] or 0
    refunded = Refund.objects.filter(status=Refund.Status.COMPLETED).aggregate(total=Sum("amount"))["total"] or 0
    platform_commissions = CommissionTransaction.objects.aggregate(total=Sum("commission_amount"))["total"] or 0
    pending_payouts = Payout.objects.filter(status="pending").aggregate(total=Sum("amount"))["total"] or 0

    by_method = {
        row["method"]: row["total"]
        for row in Payment.objects.filter(status=Payment.Status.SUCCESS)
        .values("method").annotate(total=Sum("amount"))
    }

    sections = [
        {
            "heading": "Synthèse financière",
            "kpis": [
                ("Volume payé", _money(revenue)),
                ("Remboursé", _money(refunded)),
                ("Commissions plateforme", _money(platform_commissions)),
                ("Payouts en attente", _money(pending_payouts)),
            ],
            "table": {
                "columns": ["Méthode", "Volume réglé"],
                "rows": [[method, _money(total)] for method, total in by_method.items()],
            },
        },
        {
            "heading": "Derniers paiements",
            "table": {
                "columns": ["Paiement", "Méthode", "Statut", "Montant", "Payé le"],
                "rows": _recent(
                    Payment.objects.select_related("order"),
                    [lambda p: str(p.id)[:8], lambda p: p.method, lambda p: p.get_status_display(),
                     lambda p: _money(p.amount),
                     lambda p: (p.paid_at or p.created_at).strftime("%d/%m/%Y %H:%M")],
                ),
            },
        },
    ]
    return {"title": "Rapport financier", "sections": sections}


# ---------------------------------------------------------------- sellers
def sellers_report():
    from apps.catalog.models import Store
    from apps.orders.models import Order

    top = (
        Store.objects.annotate(
            orders_count=Count("orders"),
            revenue=Sum("orders__total_amount"),
        )
        .order_by("-orders_count")[:25]
    )
    sections = [
        {
            "heading": "Top vendeurs par volume de commandes",
            "table": {
                "columns": ["Vendeur", "Email", "Boutique", "Statut", "Commandes", "CA estimé"],
                "rows": [
                    [s.owner.get_full_name() or s.owner.email, s.owner.email, s.name,
                     s.get_status_display(), s.orders_count,
                     _money(s.revenue or 0)]
                    for s in top
                ],
            },
        }
    ]
    return {"title": "Rapport vendeurs", "sections": sections}


# ---------------------------------------------------------------- stores
def stores_report():
    from apps.catalog.models import Store, Product
    from apps.orders.models import Order

    stats = (
        Store.objects.annotate(
            products_count=Count("products"),
            orders_count=Count("orders"),
        )
        .order_by("name")[:100]
    )
    sections = [
        {
            "heading": "Boutiques de la plateforme",
            "kpis": [
                ("Boutiques créées", Store.objects.count()),
                ("Boutiques actives", Store.objects.filter(status=Store.Status.ACTIVE).count()),
                ("Boutiques suspendues", Store.objects.filter(status=Store.Status.SUSPENDED).count()),
            ],
            "table": {
                "columns": ["Boutique", "Catégorie", "Statut", "Produits", "Commandes", "Créée le"],
                "rows": [
                    [s.name, s.category.name if s.category else "—", s.get_status_display(),
                     s.products_count, s.orders_count, s.created_at.strftime("%d/%m/%Y")]
                    for s in stats
                ],
            },
        }
    ]
    return {"title": "Rapport boutiques", "sections": sections}


# ---------------------------------------------------------------- orders
def orders_report():
    from apps.orders.models import Order

    breakdown = _count_breakdown(Order)
    kpis = [(label, breakdown.get(value, 0)) for value, label in [
        ("pending", "En attente"), ("paid", "Payées"), ("processing", "En traitement"),
        ("shipped", "Expédiées"), ("delivered", "Livrées"), ("cancelled", "Annulées"),
    ]]
    sections = [
        {
            "heading": "Commandes par statut",
            "kpis": kpis,
            "table": {
                "columns": ["Commande", "Client", "Boutique", "Montant", "Statut", "Date"],
                "rows": _recent(
                    Order.objects.select_related("customer", "store"),
                    [lambda o: str(o.id)[:8], lambda o: o.customer.email, lambda o: o.store.name,
                     lambda o: _money(o.total_amount), lambda o: o.get_status_display(),
                     lambda o: o.created_at.strftime("%d/%m/%Y %H:%M")],
                ),
            },
        }
    ]
    return {"title": "Rapport commandes", "sections": sections}


# ---------------------------------------------------------------- deliveries
def deliveries_report():
    from apps.orders.models import Delivery

    breakdown = _count_breakdown(Delivery)
    kpis = [(label, breakdown.get(value, 0)) for value, label in [
        ("pending", "En attente"), ("assigned", "Assignées"), ("picked_up", "Récupérées"),
        ("delivered", "Livrées"), ("cancelled", "Annulées"),
    ]]
    sections = [
        {
            "heading": "Livraisons par statut",
            "kpis": kpis,
            "table": {
                "columns": ["Commande", "Livreur", "Statut", "Créée le"],
                "rows": _recent(
                    Delivery.objects.select_related("order", "driver__user"),
                    [lambda d: str(d.order_id)[:8],
                     lambda d: d.driver.user.email if d.driver_id else "—",
                     lambda d: d.get_status_display(),
                     lambda d: d.created_at.strftime("%d/%m/%Y %H:%M")],
                ),
            },
        }
    ]
    return {"title": "Rapport livraisons", "sections": sections}


# ---------------------------------------------------------------- kyc
def kyc_report():
    from apps.kyc.models import SellerKYC, DriverKYC

    seller = _count_breakdown(SellerKYC)
    driver = _count_breakdown(DriverKYC)

    def _rows():
        for doc in SellerKYC.objects.select_related("seller").order_by("-created_at")[:10]:
            yield (doc.owner_type, doc.seller.email, doc.get_status_display(),
                   (doc.submitted_at or doc.created_at).strftime("%d/%m/%Y %H:%M"))
        for doc in DriverKYC.objects.select_related("driver").order_by("-created_at")[:10]:
            yield (doc.owner_type, doc.driver.email, doc.get_status_display(),
                   (doc.submitted_at or doc.created_at).strftime("%d/%m/%Y %H:%M"))

    sections = [
        {
            "heading": "Dossiers vendeurs (KYC)",
            "kpis": [(label, seller.get(value, 0)) for value, label in [
                ("SUBMITTED", "Soumis"), ("UNDER_REVIEW", "En revue"),
                ("VERIFIED", "Vérifiés"), ("REJECTED", "Rejetés"),
                ("SUSPENDED", "Suspendus"), ("BLOCKED", "Bloqués"),
            ]],
        },
        {
            "heading": "Dossiers livreurs (KYC)",
            "kpis": [(label, driver.get(value, 0)) for value, label in [
                ("SUBMITTED", "Soumis"), ("UNDER_REVIEW", "En revue"),
                ("VERIFIED", "Vérifiés"), ("REJECTED", "Rejetés"),
            ]],
            "table": {
                "columns": ["Type", "Propriétaire", "Statut", "Soumis le"],
                "rows": list(_rows()),
            },
        },
    ]
    return {"title": "Rapport KYC", "sections": sections}


# ---------------------------------------------------------------- complaints
def complaints_report():
    from apps.complaints.models import Complaint

    by_status = _count_breakdown(Complaint)
    by_category = {row["category"]: row["total"] for row in Complaint.objects.values("category").annotate(total=Count("id"))}
    sections = [
        {
            "heading": "Plaintes par statut",
            "kpis": [(label, by_status.get(value, 0)) for value, label in [
                ("open", "Ouvertes"), ("assigned", "Assignées"),
                ("in_progress", "En traitement"), ("escalated", "Escaladées"),
                ("resolved", "Résolues"), ("closed", "Clôturées"),
            ]],
            "table": {
                "columns": ["Catégorie", "Nombre", "Statut", "Priorité", "Référence", "Créée le"],
                "rows": [
                    [c.get_category_display(), by_category.get(c.category, 0), c.get_status_display(),
                     c.get_priority_display(), c.reference, c.created_at.strftime("%d/%m/%Y %H:%M")]
                    for c in Complaint.objects.order_by("-created_at")[:20]
                ],
            },
        }
    ]
    return {"title": "Rapport plaintes", "sections": sections}


# ---------------------------------------------------------------- refunds
def refunds_report():
    from apps.payments.models import Refund

    by_status = _count_breakdown(Refund)
    kpis = [(label, by_status.get(value, 0)) for value, label in [
        ("pending", "En attente"), ("approved", "Approuvés"),
        ("rejected", "Rejetés"), ("completed", "Remboursés"),
    ]]
    sections = [
        {
            "heading": "Remboursements par statut",
            "kpis": kpis,
            "table": {
                "columns": ["ID", "Paiement", "Montant", "Statut", "Motif", "Créé le"],
                "rows": _recent(
                    Refund.objects.select_related("payment"),
                    [lambda r: r.id, lambda r: str(r.payment_id)[:8], lambda r: _money(r.amount),
                     lambda r: r.get_status_display(),
                     lambda r: (r.reason or "")[:80].replace("\n", " "),
                     lambda r: r.created_at.strftime("%d/%m/%Y %H:%M")],
                ),
            },
        }
    ]
    return {"title": "Rapport remboursements", "sections": sections}


GENERATORS = {
    "global": global_report,
    "finance": finance_report,
    "sellers": sellers_report,
    "stores": stores_report,
    "orders": orders_report,
    "deliveries": deliveries_report,
    "kyc": kyc_report,
    "complaints": complaints_report,
    "refunds": refunds_report,
}


# ---------------------------------------------------------------- rendus
def render_csv(report):
    """Sérialise un rapport en CSV (une section = un tableau)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["SUNU MALL — " + report["title"]])
    writer.writerow(["Généré le", timezone.now().strftime("%d/%m/%Y %H:%M")])
    writer.writerow([])
    for section in report["sections"]:
        writer.writerow([section["heading"].upper()])
        for label, value in section.get("kpis", []):
            writer.writerow([label, value])
        table = section.get("table")
        if table:
            writer.writerow([])
            writer.writerow(table["columns"])
            for row in table["rows"]:
                writer.writerow([str(cell).replace("\n", " ") for cell in row])
        writer.writerow([])
    return buffer.getvalue().encode("utf-8-sig")


def render_pdf(report):
    """Sérialise un rapport en PDF (réutilise le builder minimal du projet)."""
    from apps.complaints.pdf import PDFBuilder

    builder = PDFBuilder()
    builder.header(report["title"], "Export administrateur")
    builder.footer_note = "Rapport administrateur"
    builder.hline()
    builder.text(f"Généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')}", size=9)
    builder.hline()
    for section in report["sections"]:
        builder.text(section["heading"], size=11, bold=True, leading=16)
        for label, value in section.get("kpis", []):
            builder.key_value(label, value)
        builder.hline()
        table = section.get("table")
        if table:
            builder.text(" | ".join(table["columns"]), size=8, bold=True, leading=12)
            for row in table["rows"]:
                builder.text(" | ".join(str(cell) for cell in row), size=8, leading=12)
        builder.hline()
    return builder.finish()