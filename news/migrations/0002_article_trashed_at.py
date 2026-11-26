from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("news", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="article",
            name="trashed_at",
            field=models.DateTimeField(
                "movida para a lixeira em", null=True, blank=True, editable=False,
            ),
        ),
    ]
