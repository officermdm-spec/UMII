from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.inventory.models import Inventory, StockTransaction, Warehouse
from apps.inventory.services import (
    StockError,
    allocate_stock,
    available_stock,
    inventory_health,
    record_stock_transaction,
    visible_inventory_q,
)

User = get_user_model()


class InventoryTransactionTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()

    def test_stock_changes_only_through_transactions(self):
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=10,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="TEST",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertEqual(StockTransaction.objects.count(), 1)
        self.assertEqual(available_stock(self.product, self.warehouse), 10)

    def test_stock_cannot_go_negative(self):
        with self.assertRaises(StockError):
            record_stock_transaction(
                product=self.product,
                warehouse=self.warehouse,
                quantity=-1,
                transaction_type=StockTransaction.Type.ADJUSTMENT,
                reference="TEST",
            )

    def test_reserve_reduces_available_not_current(self):
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=2,
            transaction_type=StockTransaction.Type.RESERVE,
            reference="ORD-1",
        )
        self.assertEqual(available_stock(self.product, self.warehouse), 3)

    def test_zero_quantity_rejected(self):
        with self.assertRaises(StockError):
            record_stock_transaction(
                product=self.product,
                warehouse=self.warehouse,
                quantity=0,
                transaction_type=StockTransaction.Type.ADJUSTMENT,
                reference="ZERO",
            )

    def test_damage_requires_negative_quantity(self):
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        with self.assertRaises(StockError):
            record_stock_transaction(
                product=self.product,
                warehouse=self.warehouse,
                quantity=1,
                transaction_type=StockTransaction.Type.DAMAGE,
                reference="DMG",
            )
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=-1,
            transaction_type=StockTransaction.Type.DAMAGE,
            reference="DMG",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 4)

    def test_inventory_health_labels(self):
        from apps.inventory.models import Inventory

        inv, _ = Inventory.objects.get_or_create(
            product=self.product,
            warehouse=self.warehouse,
            defaults={"current_stock": 2, "reserved_stock": 0},
        )
        Inventory.objects.filter(pk=inv.pk).update(current_stock=2, reserved_stock=0)
        inv.refresh_from_db()
        self.product.min_stock_level = 5
        self.product.save(update_fields=["min_stock_level"])
        self.assertEqual(inventory_health(inv), "low")
        inv.current_stock = 0
        inv.save(update_fields=["current_stock"])
        self.assertEqual(inventory_health(inv), "out")


class InventoryStaffViewTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()
        self.staff = User.objects.create_user(
            username="stock",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.INVENTORY],
        )
        self.client.login(username="stock", password="pass12345")

    def test_adjustment_adds_stock_and_updates_min_level(self):
        response = self.client.post(
            reverse("inventory:adjust"),
            {
                "product": self.product.pk,
                "warehouse": self.warehouse.pk,
                "quantity": "7",
                "transaction_type": StockTransaction.Type.ADJUSTMENT,
                "min_stock_level": "3",
                "notes": "Opening",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)
        self.assertEqual(self.product.min_stock_level, 3)
        self.assertTrue(
            StockTransaction.objects.filter(
                product=self.product, transaction_type=StockTransaction.Type.ADJUSTMENT
            ).exists()
        )

    def test_min_stock_update_and_low_filter(self):
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=2,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        response = self.client.post(
            reverse("inventory:min_stock"),
            {"product": self.product.pk, "min_stock_level": "10"},
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.min_stock_level, 10)
        listing = self.client.get(reverse("inventory:list"), {"status": "low"})
        self.assertContains(listing, self.product.sku)

    def test_barcode_search_filters_inventory(self):
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=2,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        listing = self.client.get(reverse("inventory:list"), {"q": self.product.barcode})
        self.assertContains(listing, self.product.name)
        self.assertContains(listing, self.product.barcode)

    def test_empty_unused_warehouse_row_is_hidden(self):
        from apps.inventory.models import Inventory

        Inventory.objects.create(product=self.product, warehouse=self.warehouse)
        listing = self.client.get(reverse("inventory:list"))
        self.assertNotContains(listing, self.product.sku)

    def test_warehouse_module_crud(self):
        self.staff.allowed_modules = [MODULES.INVENTORY, MODULES.WAREHOUSES]
        self.staff.save(update_fields=["allowed_modules"])
        response = self.client.post(
            reverse("inventory:warehouse_create"),
            {"name": "Karachi DC", "code": "khi", "address": "Korangi", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        warehouse = Warehouse.objects.get(code="KHI")
        listing = self.client.get(reverse("inventory:warehouse_list"))
        self.assertContains(listing, "Karachi DC")
        self.assertContains(listing, warehouse.code)


class AllocateStockTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()
        self.other = Warehouse.objects.create(name="Lahore", code="LHR")

    def test_allocate_prefers_warehouse_that_can_fulfill(self):
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=2,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="MAIN",
        )
        record_stock_transaction(
            product=self.product,
            warehouse=self.other,
            quantity=10,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="LHR",
        )
        parts = allocate_stock(self.product, 6)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0][0], self.other)
        self.assertEqual(parts[0][1], 6)

    def test_visible_inventory_excludes_untouched_zero_rows(self):
        from apps.inventory.models import Inventory

        ghost = Inventory.objects.create(product=self.product, warehouse=self.warehouse)
        live, _ = Inventory.objects.get_or_create(product=self.product, warehouse=self.other)
        Inventory.objects.filter(pk=live.pk).update(current_stock=4)
        visible = Inventory.objects.filter(visible_inventory_q())
        self.assertNotIn(ghost, visible)
        self.assertIn(live, visible)
