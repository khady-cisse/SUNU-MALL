"""
Migration de données : limites produits alignées sur la spec Espace Vendeur (§31).

Starter : 10 produits ; Pro : 30 produits ; Business : illimité (None).
Le seed (0008_seed_plans) et ses ajustements (0006/0007/0009) avaient posé
20 / 100 produits pour Starter/Pro. Cette migration corrige les plans EXISTANTS
par leur code stable — les bases neuves partent directement du bon `seed_default_plans`.
"""
from django.db import migrations


SPEC_PLAN_LIMITS = {"STARTER": 10, "PRO": 30, "BUSINESS": None}
LEGACY_PLAN_LIMITS = {"STARTER": 20, "PRO": 100, "BUSINESS": None}


def apply_spec_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")
    for code in ("STARTER", "PRO", "BUSINESS"):
        SubscriptionPlan.objects.filter(code=code).update(max_products=SPEC_PLAN_LIMITS[code])


def revert_limits(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")
    for code in ("STARTER", "PRO", "BUSINESS"):
        SubscriptionPlan.objects.filter(code=code).update(max_products=LEGACY_PLAN_LIMITS[code])


class Migration(migrations.Migration):

    dependencies = [
        ("monetization", "0010_plan_renames"),
    ]

    operations = [
        migrations.RunPython(apply_spec_limits, revert_limits),
    ]