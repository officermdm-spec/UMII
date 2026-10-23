from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="grnitem",
            name="mrp",
        ),
    ]
