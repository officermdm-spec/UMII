from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import StaffModule, User
from apps.categories.models import Category
from apps.inventory.models import Warehouse
from apps.inventory.services import get_default_warehouse, record_stock_transaction
from apps.inventory.models import StockTransaction
from apps.products.models import Brand, Product
from apps.promotions.models import Promotion
from apps.vendors.models import Vendor


class Command(BaseCommand):
    help = "Create a small demo catalog for local testing."

    def handle(self, *args, **options):
        User = get_user_model()
        staff, created = User.objects.get_or_create(
            username="manager",
            defaults={
                "email": "manager@example.com",
                "user_type": User.UserType.STAFF,
                "allowed_modules": list(StaffModule.values),
                "first_name": "Store",
                "last_name": "Manager",
                "is_staff": True,
            },
        )
        if created:
            staff.set_password("manager123")
            staff.save()
        elif not staff.allowed_modules:
            staff.allowed_modules = list(StaffModule.values)
            staff.save(update_fields=["allowed_modules"])

        customer, created = User.objects.get_or_create(
            username="customer",
            defaults={
                "email": "customer@example.com",
                "user_type": User.UserType.CUSTOMER,
                "first_name": "Ayesha",
                "last_name": "Khan",
                "phone": "03001234567",
            },
        )
        if created:
            customer.set_password("customer123")
            customer.save()

        tree = {
            "Garments": ["Men", "Women", "Kids"],
            "Grocery": ["Food", "Beverages", "Household"],
            "Electronics": ["Mobiles", "Computers", "Audio"],
            "Shoes": ["Men Shoes", "Women Shoes"],
            "Accessories": ["Bags", "Watches"],
        }
        categories = {}
        for parent_name, children in tree.items():
            parent, _ = Category.objects.get_or_create(
                slug=slugify(parent_name),
                defaults={"name": parent_name, "description": f"{parent_name} category"},
            )
            categories[parent_name] = parent
            for child in children:
                cat, _ = Category.objects.get_or_create(
                    slug=slugify(child),
                    defaults={"name": child, "parent": parent},
                )
                categories[child] = cat

        vendor, _ = Vendor.objects.get_or_create(
            name="Horizon Supplies",
            defaults={
                "company_name": "Horizon Supplies Pvt Ltd",
                "contact_person": "Ali Raza",
                "phone": "021111222333",
                "email": "vendor@example.com",
                "city": "Karachi",
                "tax_ntn": "1234567-8",
                "bank_name": "HBL",
                "bank_account": "001122334455",
            },
        )
        brand, _ = Brand.objects.get_or_create(name="ShopHub Basics", defaults={"slug": "shophub-basics"})
        warehouse = get_default_warehouse()

        products = [
            ("Classic Cotton Tee", "GAR-TEE-001", "Men", Decimal("1499"), Decimal("700"), "M", "White"),
            ("Running Sneakers", "SHO-SNK-002", "Men Shoes", Decimal("6499"), Decimal("3200"), "42", "Black"),
            ("Wireless Earbuds", "ELE-EAR-003", "Audio", Decimal("4499"), Decimal("2100"), "", "Black"),
            ("Basmati Rice 5kg", "GRO-RIC-004", "Food", Decimal("1650"), Decimal("1200"), "", ""),
            ("Leather Handbag", "ACC-BAG-005", "Bags", Decimal("6999"), Decimal("3100"), "", "Brown"),
        ]
        for name, sku, cat, sell, cost, size, color in products:
            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "selling_price": sell,
                    "purchase_price": cost,
                    "category": categories[cat],
                    "vendor": vendor,
                    "brand": brand,
                    "description": f"Demo product: {name}",
                    "size": size,
                    "color": color,
                    "unit": "pcs",
                    "min_stock_level": 3,
                    "is_active": True,
                },
            )
            if created or product.stock_quantity == 0:
                record_stock_transaction(
                    product=product,
                    warehouse=warehouse,
                    quantity=20,
                    transaction_type=StockTransaction.Type.CORRECTION,
                    reference="SEED",
                    notes="Demo opening stock",
                )

        now = timezone.now()
        Promotion.objects.get_or_create(
            code="WELCOME10",
            defaults={
                "name": "Welcome 10%",
                "discount_type": Promotion.DiscountType.PERCENTAGE,
                "value": Decimal("10.00"),
                "apply_to": Promotion.ApplyTo.ALL,
                "start_date": now,
                "end_date": now + timedelta(days=90),
                "min_order_amount": Decimal("1000.00"),
                "max_discount": Decimal("1500.00"),
                "usage_limit": 1000,
                "is_active": True,
            },
        )
        self.stdout.write(self.style.SUCCESS("Demo catalog ready."))
        self.stdout.write("Staff login: manager / manager123")
        self.stdout.write("Customer login: customer / customer123")
