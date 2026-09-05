"""
App IA — intégrée dans le backend Django pour l'instant (décision actuelle),
mais conçue pour pouvoir être extraite en service à part plus tard si besoin
(voir docs/architecture.md, section "App IA").

Règle : ne bloquer une requête HTTP qu'avec un traitement réellement rapide
(agrégat SQL, appel API texte de quelques secondes — voir services.py pour
les appels Claude). Un vrai traitement lourd (inférence locale, batch...)
irait dans une tâche Celery à part, mais aucune fonctionnalité actuelle de
cette app n'en a besoin.

Fonctionnalités actuelles :
- Recommandations personnalisées par co-achat (RecommendationLog, calcul
  synchrone — voir compute_for_user ci-dessous et apps/ia/views.py).
- Génération de description produit + assistant client (services.py,
  appels réels à Claude).
"""
from django.db import models
from apps.users.models import User


class RecommendationLog(models.Model):
    """
    Historique des recommandations calculées pour chaque utilisateur —
    utile pour mesurer dans le temps si les recommandations poussent
    réellement à l'achat (comparer produits recommandés vs achetés
    ensuite), pas seulement pour servir la recommandation du moment.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recommendation_logs")
    payload = models.JSONField(help_text="Contenu : {'recommended_product_ids': [...]}")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def compute_for_user(user, limit=8):
        """
        Recommandations personnalisées par co-achat : à partir des produits
        que cet utilisateur a déjà commandés, trouve les produits les plus
        souvent commandés *avec* eux par d'autres clients (même logique que
        ProductViewSet.similar, appliquée à l'ensemble de l'historique du
        client plutôt qu'à un seul produit). Aucun appel IA générative —
        un agrégat SQL suffit et reste instantané.

        Si le client n'a encore aucune commande (nouveau compte), renvoie
        une liste vide plutôt que d'inventer une recommandation : mieux
        vaut ne rien afficher qu'afficher du hasard.
        """
        from django.db import models as dj_models
        from apps.orders.models import Order, OrderItem

        bought_product_ids = list(
            OrderItem.objects.filter(order__customer=user)
            .exclude(order__status=Order.Status.CANCELLED)
            .values_list("product_variant__product_id", flat=True)
            .distinct()
        )

        recommended_ids = []
        if bought_product_ids:
            order_ids = (
                OrderItem.objects.filter(product_variant__product_id__in=bought_product_ids)
                .exclude(order__status=Order.Status.CANCELLED)
                .values_list("order_id", flat=True)
            )
            recommended_ids = list(
                OrderItem.objects.filter(order_id__in=order_ids)
                .exclude(product_variant__product_id__in=bought_product_ids)
                .values("product_variant__product_id")
                .annotate(freq=dj_models.Count("id"))
                .order_by("-freq")
                .values_list("product_variant__product_id", flat=True)[:limit]
            )

        payload = {"recommended_product_ids": [str(pid) for pid in recommended_ids]}
        log = RecommendationLog.objects.create(user=user, payload=payload)

        # Limite la croissance : ce fichier est écrit à chaque visite de page
        # d'accueil pour un utilisateur connecté. Conserver uniquement la
        # dernière entrée par utilisateur (les plus anciennes n'ont pas de
        # valeur : la recommandation courante est réécrite à chaque calcul).
        RecommendationLog.objects.filter(user=user).exclude(pk=log.pk).delete()
        return log

    def __str__(self):
        return f"Recommandation pour {self.user.username} — {self.created_at:%Y-%m-%d}"
