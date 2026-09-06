"""
Plans de commission (spec §2/§5) : BASIQUE / PRO / BUSINESS.

Les offres historiques Standard/Premium/Premium+ (qui ne servaient qu'à la
limite produits) deviennent les plans de commission SUNU MALL :
    Standard  → BASIC    (5 000 FCFA, 5 %, 30 j)
    Premium   → PRO      (10 000 FCFA, 3 %, 30 j)
    Premium+  → BUSINESS (20 000 FCFA, 1 %, 30 j)

L'identité d'un plan reste le nom dans `SubscriptionPlan` (une seule source
de vérité) ; `apps.commissions` mémorise ce nom comme instantané sur chaque
vente. Les limites produits (max_products) sont conservées telles quelles.
"""
from django.db import migrations, models


PLAN_REMAP = {
    "Standard": {"name": "BASIC", "price": 5000, "commission_rate": 5, "duration_days": 30},
    "Premium": {"name": "PRO", "price": 10000, "commission_rate": 3, "duration_days": 30},
    "Premium+": {"name": "BUSINESS", "price": 20000, "commission_rate": 1, "duration_days": 30},
}


def remap_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")
    for old_name, data in PLAN_REMAP.items():
        SubscriptionPlan.objects.filter(name=old_name).update(
            name=data["name"], price=data["price"],
            commission_rate=data["commission_rate"], duration_days=data["duration_days"],
            is_active=True,
        )


def rollback_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")
    for new_name, data in PLAN_REMAP.items():
        SubscriptionPlan.objects.filter(name=data["name"]).update(
            name=new_name, price=0 if new_name == "Standard" else (15000 if new_name == "Premium" else 35000),
            commission_rate=0, duration_days=30,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("monetization", "0006_set_plan_product_limits"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="commission_rate",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="duration_days",
            field=models.IntegerField(default=30),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(remap_plans, rollback_plans),
    ]