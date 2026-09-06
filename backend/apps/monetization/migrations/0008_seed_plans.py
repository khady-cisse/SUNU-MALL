"""
Seed des plans SUNU MALL (spec §2/§5).

Garantit que les trois plans existent dans toutes les bases (tests compris) :
    BASIC    (5 000 FCFA, 5 %, 30 j)
    PRO      (10 000 FCFA, 3 %, 30 j)
    BUSINESS (20 000 FCFA, 1 %, 30 j)

Idempotent (update_or_create) : la 0007 a déjà renommé les plans historiques,
cette migration ne fait que compléter ce qui manquerait.
"""
from django.db import migrations


PLANS = [
    {"name": "BASIC", "price": 5000, "commission_rate": 5, "duration_days": 30, "max_products": 10},
    {"name": "PRO", "price": 10000, "commission_rate": 3, "duration_days": 30, "max_products": 50},
    {"name": "BUSINESS", "price": 20000, "commission_rate": 1, "duration_days": 30, "max_products": None},
]


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")
    for plan in PLANS:
        SubscriptionPlan.objects.update_or_create(
            name=plan["name"],
            defaults={
                "price": plan["price"],
                "billing_cycle": "monthly",
                "features": {},
                "max_products": plan["max_products"],
                "commission_rate": plan["commission_rate"],
                "duration_days": plan["duration_days"],
                "is_active": True,
            },
        )


def unseed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")
    # Rollback symétrique : on restaure les offres historiques au lieu de supprimer.
    legacy = {
        "BASIC": {"name": "Standard", "price": 0},
        "PRO": {"name": "Premium", "price": 15000},
        "BUSINESS": {"name": "Premium+", "price": 35000},
    }
    for name, data in legacy.items():
        SubscriptionPlan.objects.filter(name=name).update(
            name=data["name"], price=data["price"],
            commission_rate=0, duration_days=30,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("monetization", "0007_plan_commissions"),
    ]

    operations = [
        migrations.RunPython(seed_plans, unseed_plans),
    ]