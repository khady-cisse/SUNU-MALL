"""
Ajoute Subscription.reference (SUB-YYYYMMDD-######, spec Espace Vendeur §19).

Le champ est d'abord nullable ; on le remplit ensuite pour toutes les lignes
existantes à partir de l'UUID (déterministe, unique par ligne), puis on pose la
contrainte UNIQUE.
"""
from django.db import migrations, models


def backfill_references(apps, schema_editor):
    Subscription = apps.get_model("monetization", "Subscription")
    for sub in Subscription.objects.filter(reference__isnull=True).iterator():
        day = sub.created_at.strftime("%Y%m%d") if sub.created_at else "00000000"
        suffix = (sub.id.hex[:6]).upper()
        sub.reference = f"SUB-{day}-{suffix}"
        sub.save(update_fields=["reference"])


def noop_reverse(apps, schema_editor):
    """Pas de retour arrière (le champ reste, les références gardent leur valeur)."""


class Migration(migrations.Migration):

    dependencies = [
        ("monetization", "0011_plan_limits_spec"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="reference",
            field=models.CharField(editable=False, max_length=40, null=True, unique=True),
        ),
        migrations.RunPython(backfill_references, noop_reverse),
        migrations.AlterField(
            model_name="subscription",
            name="reference",
            field=models.CharField(blank=True, editable=False, max_length=40, null=True, unique=True),
        ),
    ]