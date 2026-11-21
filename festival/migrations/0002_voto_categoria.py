import django.db.models.deletion
from django.db import migrations, models


def rellenar_categoria(apps, schema_editor):
    """Los votos existentes toman la categoría de su votación."""
    Voto = apps.get_model("festival", "Voto")
    for voto in Voto.objects.select_related("votacion").iterator():
        voto.categoria_id = voto.votacion.categoria_id
        voto.save(update_fields=["categoria"])


class Migration(migrations.Migration):

    dependencies = [
        ("festival", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="voto",
            name="categoria",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="votos", to="festival.categoria"),
        ),
        migrations.RunPython(rellenar_categoria, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="voto",
            name="categoria",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="votos", to="festival.categoria"),
        ),
        migrations.AddConstraint(
            model_name="voto",
            constraint=models.UniqueConstraint(fields=("votante", "categoria", "numero"), name="voto_unico_por_categoria"),
        ),
    ]
