from django.core.management.base import BaseCommand

from apps.inventory.models import Warehouse
from apps.payments.models import PaymentMethod


class Command(BaseCommand):
    help = "Create the default warehouse and payment methods."

    def handle(self, *args, **options):
        Warehouse.objects.get_or_create(
            code="MAIN", defaults={"name": "Main Warehouse", "address": "Head office"}
        )
        methods = [
            (PaymentMethod.Code.COD, "Cash on Delivery", "Pay when you receive the order."),
        ]
        for code, name, description in methods:
            PaymentMethod.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "is_active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS("Seeded warehouse and payment methods."))
        self.stdout.write("Next: python manage.py createsuperuser")
        self.stdout.write("Optional demo catalog: python manage.py seed_demo")
