"""
Migration de données : plan BASIC renommé STARTER (spec monétisation §11).

L'ancien seed (0008_seed_plans) créait le plan `BASIC`. Le code et les
endpoints utilisent désormais STARTER/PRO/BUSINESS comme identifiants stables.
Cette migration :
- supprime d'éventuelles collisions de code avant renommage ;
- renomme le plan `BASIC` en `STARTER` et lui pose le code `STARTER` ;
- pose les codes stables manquants sur PRO / BUSINESS.
Les plans existants (name) déjà corrects ne sont pas touchés.
"""
from django.db import migrations, models


def fix_plan_names_and_codes(apps, schema_editor):
    SubscriptionPlan = apps.get_model("monetization", "SubscriptionPlan")

    # 1. Évite toute collision de code avant le renommage (code unique).
    SubscriptionPlan.objects.filter(name="STARTER").exclude(code="STARTER").update(code=None)
    SubscriptionPlan.objects.filter(name="PRO").exclude(code="PRO").update(code=None)
    SubscriptionPlan.objects.filter(name="BUSINESS").exclude(code="BUSINESS").update(code=None)

    # 2. Renomme l'ancien plan BASIC et pose les codes stables manquants.
    SubscriptionPlan.objects.filter(name="BASIC").update(name="STARTER", code="STARTER")
    SubscriptionPlan.objects.filter(name="PRO", code__isnull=True).update(code="PRO")
    SubscriptionPlan.objects.filter(name="BUSINESS", code__isnull=True).update(code="BUSINESS")


class Migration(migrations.Migration):

    dependencies = [
        ('monetization', '0009_admin_center'),
    ]

    operations = [
        migrations.RunPython(fix_plan_names_and_codes, migrations.RunPython.noop),
    ]