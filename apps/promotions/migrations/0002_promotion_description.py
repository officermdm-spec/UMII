from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="promotion",
            name="description",
            field=models.CharField(blank=True, max_length=220),
        ),
    ]
