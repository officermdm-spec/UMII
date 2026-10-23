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
            (PaymentMethod.Code.COD, "Cash on Delivery", "Pay when you receive the order.", 1),
            (PaymentMethod.Code.ONLINE, "Online Payment", "Pay by card through the online gateway.", 2),
            (PaymentMethod.Code.BANK_TRANSFER, "Bank Transfer", "Transfer to our bank account and share the receipt.", 3),
            (PaymentMethod.Code.EASYPAISA, "Easypaisa", "Pay using your Easypaisa wallet.", 4),
            (PaymentMethod.Code.JAZZCASH, "JazzCash", "Pay using your JazzCash wallet.", 5),
        ]
        for code, name, description, sort_order in methods:
            PaymentMethod.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "sort_order": sort_order,
                    "is_active": True,
                    "instructions": description,
                },
            )
        self.stdout.write(self.style.SUCCESS("Seeded warehouse and payment methods."))
        self.stdout.write("Next: python manage.py createsuperuser")
        self.stdout.write("Optional demo catalog: python manage.py seed_demo")
