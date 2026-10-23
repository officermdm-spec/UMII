import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("reviews", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="feedback",
            name="topic",
            field=models.CharField(
                choices=[
                    ("product", "Product"),
                    ("order", "Order"),
                    ("delivery", "Delivery"),
                    ("payment", "Payment"),
                    ("website", "Website"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="feedback",
            name="rating",
            field=models.PositiveSmallIntegerField(
                default=5,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
        ),
        migrations.AddField(
            model_name="feedback",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("in_review", "In review"),
                    ("replied", "Replied"),
                    ("closed", "Closed"),
                ],
                default="new",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="feedback",
            name="staff_reply",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="feedback",
            name="replied_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="feedback",
            name="replied_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="feedback_replies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
