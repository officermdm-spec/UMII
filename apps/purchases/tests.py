from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.inventory.models import Inventory, StockTransaction
from apps.inventory.services import available_stock
from apps.purchases.models import GRN, GRNItem, ProductPurchaseHistory
from django.core.exceptions import PermissionDenied

from apps.purchases.services import GRNError, approve_grn, delete_grn, unapprove_grn

User = get_user_model()


class GRNApprovalTests(TestCase):
    def setUp(self):
        self.warehouse, _, self.vendor, self.product = build_catalog()
        self.user = User.objects.create_user(
            username="buyer", password="pass12345", user_type=User.UserType.STAFF, is_staff=True
        )

    def test_new_grn_defaults_to_pending(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.user)
        self.assertEqual(grn.status, GRN.Status.PENDING)
        self.assertTrue(grn.grn_number.startswith("GRN-"))
        self.assertEqual(grn.grn_date, timezone.localdate())
        self.assertTrue(grn.can_edit)

    def test_approve_grn_increases_stock_and_history(self):
        grn = GRN.objects.create(
            vendor=self.vendor, warehouse=self.warehouse, received_by=self.user, status=GRN.Status.PENDING
        )
        GRNItem.objects.create(
            grn=grn,
            product=self.product,
            quantity=8,
            purchase_rate=Decimal("100.00"),
        )
        approve_grn(grn, self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertTrue(
            StockTransaction.objects.filter(
                reference=grn.grn_number, transaction_type=StockTransaction.Type.GRN
            ).exists()
        )
        self.assertEqual(ProductPurchaseHistory.objects.filter(product=self.product).count(), 1)
        grn.refresh_from_db()
        self.assertEqual(grn.status, GRN.Status.APPROVED)
        self.assertFalse(grn.can_edit)
        self.assertEqual(self.product.purchase_price, Decimal("100.00"))
        self.assertEqual(grn.items.get().average_cost_after, Decimal("100.00"))

    def test_second_grn_uses_weighted_average_cost(self):
        first = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.user)
        GRNItem.objects.create(grn=first, product=self.product, quantity=10, purchase_rate=Decimal("100.00"))
        approve_grn(first, self.user)
        second = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.user)
        GRNItem.objects.create(grn=second, product=self.product, quantity=10, purchase_rate=Decimal("200.00"))
        approve_grn(second, self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price, Decimal("150.00"))
        self.assertEqual(second.items.get().average_cost_after, Decimal("150.00"))

    def test_admin_can_unapprove_grn(self):
        admin = User.objects.create_superuser("root", "root@example.com", "pass12345")
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.user)
        GRNItem.objects.create(grn=grn, product=self.product, quantity=8, purchase_rate=Decimal("100.00"))
        approve_grn(grn, self.user)
        unapprove_grn(grn, admin)
        grn.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(grn.status, GRN.Status.PENDING)
        self.assertTrue(grn.can_edit)
        self.assertIsNone(grn.approved_by)
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertEqual(ProductPurchaseHistory.objects.filter(grn=grn).count(), 0)

    def test_non_admin_cannot_unapprove_grn(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.user)
        GRNItem.objects.create(grn=grn, product=self.product, quantity=2, purchase_rate=Decimal("10.00"))
        approve_grn(grn, self.user)
        with self.assertRaises(PermissionDenied):
            unapprove_grn(grn, self.user)

    def test_approve_grn_hits_only_selected_warehouse(self):
        from apps.inventory.models import Warehouse

        other = Warehouse.objects.create(name="Lahore", code="LHR", address="Lahore")
        grn = GRN.objects.create(
            vendor=self.vendor, warehouse=other, received_by=self.user, status=GRN.Status.PENDING
        )
        GRNItem.objects.create(
            grn=grn,
            product=self.product,
            quantity=8,
            purchase_rate=Decimal("100.00"),
        )
        approve_grn(grn, self.user)
        codes = set(
            Inventory.objects.filter(product=self.product).values_list("warehouse__code", flat=True)
        )
        self.assertEqual(codes, {"LHR"})
        self.assertEqual(available_stock(self.product, other), 8)
        self.assertEqual(available_stock(self.product, self.warehouse), 0)
        self.assertEqual(available_stock(self.product), 8)
        self.assertFalse(
            StockTransaction.objects.filter(
                product=self.product, warehouse=self.warehouse, reference=grn.grn_number
            ).exists()
        )

    def test_approved_grn_cannot_be_deleted(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.user)
        GRNItem.objects.create(
            grn=grn, product=self.product, quantity=2, purchase_rate=Decimal("10.00")
        )
        approve_grn(grn, self.user)
        with self.assertRaises(GRNError):
            delete_grn(grn)


class GRNStaffViewTests(TestCase):
    def setUp(self):
        self.warehouse, _, self.vendor, self.product = build_catalog()
        self.staff = User.objects.create_user(
            username="grnstaff",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.GRN],
        )
        self.client.login(username="grnstaff", password="pass12345")

    def _item_payload(self, **overrides):
        data = {
            "vendor": self.vendor.pk,
            "invoice_number": "",
            "warehouse": self.warehouse.pk,
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-product": self.product.pk,
            "items-0-quantity": "5",
            "items-0-purchase_rate": "120.00",
            "items-0-batch_number": "B-1",
            "items-0-expiry_date": "2027-01-31",
        }
        data.update(overrides)
        return data

    def test_create_saves_pending_voucher(self):
        response = self.client.post(reverse("purchases:create"), self._item_payload())
        self.assertEqual(response.status_code, 302)
        grn = GRN.objects.get()
        self.assertEqual(grn.status, GRN.Status.PENDING)
        self.assertTrue(grn.grn_number.startswith("GRN-"))
        self.assertEqual(grn.grn_date, timezone.localdate())
        self.assertEqual(grn.items.count(), 1)
        self.assertEqual(grn.items.first().batch_number, "B-1")

    def test_list_shows_edit_delete_view_for_pending(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.staff)
        response = self.client.get(reverse("purchases:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, grn.grn_number)
        self.assertContains(response, reverse("purchases:detail", args=[grn.pk]))
        self.assertContains(response, reverse("purchases:update", args=[grn.pk]))
        self.assertContains(response, reverse("purchases:delete", args=[grn.pk]))

    def test_approved_voucher_hides_edit_and_delete(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.staff)
        GRNItem.objects.create(
            grn=grn, product=self.product, quantity=1, purchase_rate=Decimal("10.00")
        )
        approve_grn(grn, self.staff)
        response = self.client.get(reverse("purchases:list"))
        self.assertContains(response, reverse("purchases:detail", args=[grn.pk]))
        self.assertNotContains(response, reverse("purchases:update", args=[grn.pk]))
        self.assertNotContains(response, reverse("purchases:delete", args=[grn.pk]))
        self.assertEqual(self.client.get(reverse("purchases:update", args=[grn.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("purchases:delete", args=[grn.pk])).status_code, 404)

    def test_pending_can_be_deleted(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.staff)
        response = self.client.post(reverse("purchases:delete", args=[grn.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GRN.objects.filter(pk=grn.pk).exists())

    def test_barcode_lookup_finds_product(self):
        response = self.client.get(reverse("products:lookup"), {"barcode": self.product.barcode})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["id"], self.product.pk)
        missing = self.client.get(reverse("products:lookup"), {"barcode": "NOPE"})
        self.assertEqual(missing.status_code, 404)

    def test_staff_cannot_see_or_post_unapprove(self):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.staff)
        GRNItem.objects.create(grn=grn, product=self.product, quantity=1, purchase_rate=Decimal("10.00"))
        approve_grn(grn, self.staff)
        detail = self.client.get(reverse("purchases:detail", args=[grn.pk]))
        self.assertContains(detail, "This voucher is approved and locked.")
        self.assertNotContains(detail, "Unapprove")
        response = self.client.post(reverse("purchases:unapprove", args=[grn.pk]))
        self.assertEqual(response.status_code, 403)
        grn.refresh_from_db()
        self.assertEqual(grn.status, GRN.Status.APPROVED)

    def test_admin_sees_unapprove_button(self):
        User.objects.create_superuser("root", "root@example.com", "pass12345")
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.staff)
        GRNItem.objects.create(grn=grn, product=self.product, quantity=1, purchase_rate=Decimal("10.00"))
        approve_grn(grn, self.staff)
        self.client.logout()
        self.client.login(username="root", password="pass12345")
        detail = self.client.get(reverse("purchases:detail", args=[grn.pk]))
        self.assertContains(detail, "Unapprove")
        response = self.client.post(reverse("purchases:unapprove", args=[grn.pk]))
        self.assertEqual(response.status_code, 302)
        grn.refresh_from_db()
        self.assertEqual(grn.status, GRN.Status.PENDING)
