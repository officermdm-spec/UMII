from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_grant_expense_vendor_payment_methods"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="access_mode",
            field=models.CharField(
                choices=[("full", "Full access"), ("viewer", "Viewer (read only)")],
                default="full",
                help_text="Viewers can open assigned modules but cannot add, edit, or delete records.",
                max_length=20,
            ),
        ),
    ]
