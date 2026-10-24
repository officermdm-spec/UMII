from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import StaffModule
from apps.accounts.permissions import MODULES, STAFF_NAV, has_module_permission
from apps.categories.models import Category
from apps.inventory.models import Warehouse
from apps.payments.models import PaymentMethod
from apps.products.models import Product
from apps.vendors.models import Vendor

User = get_user_model()


def build_catalog():
    warehouse, _ = Warehouse.objects.get_or_create(code="MAIN", defaults={"name": "Main"})
    category = Category.objects.create(name="Electronics", slug="electronics")
    vendor = Vendor.objects.create(name="Acme", phone="03001111111")
    product = Product.objects.create(
        name="Demo Phone",
        sku="ELE-001",
        selling_price=Decimal("45000"),
        purchase_price=Decimal("30000"),
        category=category,
        vendor=vendor,
        stock_quantity=0,
        min_stock_level=2,
    )
    PaymentMethod.objects.get_or_create(
        code=PaymentMethod.Code.COD, defaults={"name": "Cash on Delivery"}
    )
    return warehouse, category, vendor, product


class PermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sales1",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.ORDERS],
            is_staff=True,
        )

    def test_staff_user_uses_selected_modules(self):
        self.assertTrue(has_module_permission(self.user, MODULES.ORDERS))
        self.assertFalse(has_module_permission(self.user, MODULES.INVENTORY))

    def test_staff_without_permission_gets_403(self):
        self.client.login(username="sales1", password="pass12345")
        response = self.client.get(reverse("inventory:adjust"))
        self.assertEqual(response.status_code, 403)

    def test_custom_staff_user_is_not_marked_as_django_admin_staff(self):
        staff_user = User.objects.create_user(
            username="plain-staff",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
        )

        self.assertFalse(staff_user.is_staff)
        self.assertEqual(staff_user.user_type, User.UserType.STAFF)

    def test_superuser_has_all_access(self):
        admin = User.objects.create_superuser("root", "root@example.com", "pass12345")
        self.assertTrue(has_module_permission(admin, MODULES.USERS))

    def test_staff_nav_covers_every_module(self):
        hidden_modules = {MODULES.EXPENSES, MODULES.VENDOR_PAYMENTS}
        self.assertEqual(
            {item["module"] for item in STAFF_NAV},
            set(StaffModule.values) - hidden_modules,
        )
        labels = {item["label"] for item in STAFF_NAV}
        self.assertIn("Warehouses", labels)
        self.assertIn("Brands", labels)
        self.assertNotIn("Expenses", labels)
        self.assertNotIn("Vendor Payments", labels)
        self.assertIn("Payment Methods", labels)

    def test_permissions_page_lists_every_module(self):
        User.objects.create_superuser("root", "root@example.com", "pass12345")
        staff = User.objects.create_user(
            username="picker",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
        )
        self.client.login(username="root", password="pass12345")
        response = self.client.get(reverse("accounts:permissions"), {"user": staff.pk})
        self.assertEqual(response.status_code, 200)
        for value, _label in StaffModule.choices:
            self.assertContains(response, f'value="{value}"')

    def test_viewer_cannot_change_data(self):
        User.objects.create_user(
            username="reader",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.CATEGORIES, MODULES.ACCOUNTING],
            access_mode=User.AccessMode.VIEWER,
        )
        self.client.login(username="reader", password="pass12345")
        self.assertEqual(self.client.get(reverse("categories:list")).status_code, 200)
        response = self.client.post(
            reverse("categories:create"),
            {"name": "Blocked", "slug": "blocked", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 403)

    def test_user_form_lists_every_module(self):
        User.objects.create_superuser("root", "root@example.com", "pass12345")
        self.client.login(username="root", password="pass12345")
        response = self.client.get(reverse("accounts:user_create"))
        self.assertEqual(response.status_code, 200)
        for value, _label in StaffModule.choices:
            self.assertContains(response, f'value="{value}"')
