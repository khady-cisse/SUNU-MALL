"""
Rend la marketplace vierge en supprimant toutes les données de démonstration
créées par `seed_demo` : boutiques, produits, images, stocks, avis,
sponsoring, commandes de démo et comptes `demo.*@sunumall.com`.

Usage :
    python manage.py flush_demo

Idempotent : relancer le script ne supprime que les données portant la
signature de démo (comptes `demo.*` et boutiques/produits associés) et cascade
le reste. Les catégories, catégories de boutiques et plans d'abonnement sont
conservés (ils proviennent de migrations) pour garder un site structuré mais
vierge.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Supprime les données de démonstration (boutiques, produits, comptes demo) pour un site vierge."

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.analytics.models import SalesStatistic, TrafficStatistic
        from apps.catalog.models import (
            Inventory,
            Product,
            ProductImage,
            ProductVariant,
            Review,
            Store,
        )
        from apps.kyc.models import SellerKYC
        from apps.monetization.models import SponsoredProduct
        from apps.orders.models import (
            Delivery,
            DeliveryEvent,
            DeliveryPickup,
            DeliveryTracking,
            GlobalOrder,
            Order,
            OrderHistory,
            OrderItem,
        )
        from apps.shopping.models import CartItem, WishlistItem

        User = get_user_model()
        demo_users = User.objects.filter(email__startswith="demo.")
        demo_stores = Store.objects.filter(owner__email__startswith="demo.")

        before = {
            "boutiques": Store.objects.count(),
            "produits": Product.objects.count(),
            "images": ProductImage.objects.count(),
            "variants": ProductVariant.objects.count(),
            "stocks": Inventory.objects.count(),
            "avis": Review.objects.count(),
            "commandes": Order.objects.count(),
            "sponsorisés": SponsoredProduct.objects.count(),
            "comptes demo": demo_users.count(),
        }

        demo_store_ids = list(demo_stores.values_list("id", flat=True))
        demo_user_ids = list(demo_users.values_list("id", flat=True))
        demo_product_ids = list(
            Product.objects.filter(store_id__in=demo_store_ids).values_list(
                "id", flat=True
            )
        )
        demo_order_ids = list(
            Order.objects.filter(store_id__in=demo_store_ids).values_list(
                "id", flat=True
            )
        )
        demo_global_ids = list(
            GlobalOrder.objects.filter(orders__store_id__in=demo_store_ids).values_list(
                "id", flat=True
            )
        )
        demo_delivery_ids = list(
            Delivery.objects.filter(order_id__in=demo_order_ids).values_list(
                "id", flat=True
            )
        )

        # --- 1) Dépendances « protégées » commandes / livraisons -------------
        from apps.complaints.models import (
            Complaint,
            ComplaintAttachment,
            ComplaintTimeline,
            SupportTicket,
            TicketMessage,
        )
        from apps.payments.models import Payment, Refund
        from apps.commissions.models import (
            CommissionTransaction,
            PlatformTransaction,
            WalletTransaction,
        )
        from apps.monetization.models import Notification

        demo_complaint_ids = list(
            Complaint.objects.filter(order_id__in=demo_order_ids).values_list(
                "id", flat=True
            )
        )
        demo_complaint_ids += list(
            Complaint.objects.filter(store_id__in=demo_store_ids).values_list(
                "id", flat=True
            )
        )

        Payment.objects.filter(order_id__in=demo_order_ids).delete()
        Payment.objects.filter(global_order_id__in=demo_global_ids).delete()
        Refund.objects.filter(payment__order_id__in=demo_order_ids).delete()
        Refund.objects.filter(payment__global_order_id__in=demo_global_ids).delete()

        CommissionTransaction.objects.filter(order_id__in=demo_order_ids).delete()
        PlatformTransaction.objects.filter(order_id__in=demo_order_ids).delete()
        WalletTransaction.objects.filter(order_id__in=demo_order_ids).delete()

        ComplaintTimeline.objects.filter(complaint_id__in=demo_complaint_ids).delete()
        ComplaintTimeline.objects.filter(actor_id__in=demo_user_ids).delete()
        ComplaintAttachment.objects.filter(complaint_id__in=demo_complaint_ids).delete()
        Complaint.objects.filter(id__in=demo_complaint_ids).delete()
        TicketMessage.objects.filter(ticket__requester_id__in=demo_user_ids).delete()
        SupportTicket.objects.filter(requester_id__in=demo_user_ids).delete()

        DeliveryEvent.objects.filter(delivery_id__in=demo_delivery_ids).delete()
        DeliveryTracking.objects.filter(delivery_id__in=demo_delivery_ids).delete()
        DeliveryPickup.objects.filter(delivery_id__in=demo_delivery_ids).delete()
        DeliveryPickup.objects.filter(store_id__in=demo_store_ids).delete()
        Delivery.objects.filter(id__in=demo_delivery_ids).delete()

        Notification.objects.filter(user_id__in=demo_user_ids).delete()

        OrderItem.objects.filter(order_id__in=demo_order_ids).delete()
        OrderHistory.objects.filter(order_id__in=demo_order_ids).delete()
        Order.objects.filter(id__in=demo_order_ids).delete()
        GlobalOrder.objects.filter(id__in=demo_global_ids).delete()

        # --- 2) Produits et dépendances du catalogue --------------------------
        WishlistItem.objects.filter(product_id__in=demo_product_ids).delete()
        CartItem.objects.filter(
            product_variant__product_id__in=demo_product_ids
        ).delete()
        Review.objects.filter(product_id__in=demo_product_ids).delete()
        SponsoredProduct.objects.filter(product_id__in=demo_product_ids).delete()
        Inventory.objects.filter(variant__product_id__in=demo_product_ids).delete()
        ProductVariant.objects.filter(product_id__in=demo_product_ids).delete()
        ProductImage.objects.filter(product_id__in=demo_product_ids).delete()
        Product.objects.filter(id__in=demo_product_ids).delete()

        # --- 3) Boutiques, stats et comptes de démo ---------------------------
        SalesStatistic.objects.filter(store_id__in=demo_store_ids).delete()
        TrafficStatistic.objects.filter(store_id__in=demo_store_ids).delete()
        Store.objects.filter(id__in=demo_store_ids).delete()

        SellerKYC.objects.filter(seller_id__in=demo_user_ids).delete()
        demo_users.delete()

        after = {
            "boutiques": Store.objects.count(),
            "produits": Product.objects.count(),
            "images": ProductImage.objects.count(),
            "variants": ProductVariant.objects.count(),
            "stocks": Inventory.objects.count(),
            "avis": Review.objects.count(),
            "commandes": Order.objects.count(),
            "sponsorisés": SponsoredProduct.objects.count(),
            "comptes demo": User.objects.filter(email__startswith="demo.").count(),
        }

        self.stdout.write(self.style.SUCCESS("Données de démonstration supprimées."))
        for key in before:
            self.stdout.write(f"  {key}: {before[key]} -> {after[key]}")
