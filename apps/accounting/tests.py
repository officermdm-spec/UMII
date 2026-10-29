from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.accounting.forms import ExpenseForm
from apps.accounting.models import Account, AccountingPosting, Expense, JournalEntry
from apps.accounting.services import account_balance, ensure_accounts, period_totals, post_sale_event
from apps.customers.models import Address
from apps.inventory.costing import layer_value
from apps.inventory.models import InventoryCostLayer
from apps.orders.models import CartItem, Order
from apps.orders.services import change_order_status, place_order
from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import mark_paid
from apps.products.barcode import BarcodeLookupError, get_product_by_barcode, render_barcode_png
from apps.products.models import Product
from apps.purchases.models import GRN, GRNItem
from apps.purchases.services import GRNError, approve_grn
from apps.returns.models import ReturnItem, ReturnRequest
from apps.returns.services import update_return_status

User = get_user_model()


class SessionDict(dict):
    modified = False


class ExpenseFormTests(SimpleTestCase):
    def test_expense_form_only_needs_category_and_transaction_details(self):
        form = ExpenseForm(
            data={
                "category": Expense.Category.DELIVERY,
                "amount": "100.00",
                "date": "2026-10-24",
                "payment_account": "cash",
                "reference": "",
                "description": "",
            }
        )

        self.assertNotIn("title", form.fields)
        self.assertNotIn("notes", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        expense = form.save(commit=False)
        self.assertEqual(expense.title, "")
        self.assertEqual(expense.notes, "")


class RemovedAccountingPagesTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="accounting-ui",
            password="test-pass-12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.ACCOUNTING],
        )
        self.client.force_login(self.staff)

    def test_cash_bank_page_is_removed(self):
        response = self.client.get("/staff/accounting/cash-bank/")
        self.assertEqual(response.status_code, 404)

    def test_tax_summary_report_is_removed(self):
        response = self.client.get(reverse("accounting:report", args=["tax-summary"]))
        self.assertEqual(response.status_code, 404)

    def test_cash_and_bank_reports_are_removed(self):
        for account in ("cash", "bank"):
            with self.subTest(account=account):
                response = self.client.get(reverse("accounting:report", args=[account]))
                self.assertEqual(response.status_code, 404)

    def test_dashboard_hides_cash_and_bank_but_keeps_accounting(self):
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, ">Cash<")
        self.assertNotContains(response, ">Bank<")
        self.assertContains(response, "Total sales")
        self.assertContains(response, "Inventory value")

    def test_tax_summary_link_is_not_shown_in_reports(self):
        response = self.client.get(reverse("accounting:report", args=["profit-loss"]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Tax summary")

    def test_other_income_table_and_unused_account_are_removed(self):
        self.assertNotIn("accounting_otherincome", connection.introspection.table_names())
        self.assertFalse(Account.objects.filter(code="4020").exists())


class AccountingLineCleaningTests(TestCase):
    def test_clean_lines_fetches_accounts_in_one_query(self):
        from apps.accounting.services import _clean_lines

        ensure_accounts()
        lines = [
            {"account": "1100", "debit": Decimal("10.00")},
            {"account": "4000", "credit": Decimal("10.00")},
        ]

        with CaptureQueriesContext(connection) as queries:
            cleaned = _clean_lines(lines)

        self.assertEqual(len(queries), 1)
        self.assertEqual([line["account"].code for line in cleaned], ["1100", "4000"])


def make_request(user):
    return type("R", (), {"user": user, "session": SessionDict()})()


class BarcodeTests(TestCase):
    def setUp(self):
        self.warehouse, self.category, self.vendor, self.product = build_catalog()
        self.staff = User.objects.create_user(
            username="pm",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.PRODUCTS, MODULES.GRN],
        )

    def test_product_gets_unique_barcode_on_create(self):
        self.assertTrue(self.product.barcode)
        self.assertTrue(self.product.barcode.startswith("FP"))
        other = Product.objects.create(
            name="Other",
            sku="OTH-001",
            selling_price=Decimal("10.00"),
            purchase_price=Decimal("5.00"),
            category=self.category,
            vendor=self.vendor,
        )
        self.assertNotEqual(self.product.barcode, other.barcode)

    def test_edit_does_not_change_barcode(self):
        original = self.product.barcode
        self.product.selling_price = Decimal("50000")
        self.product.purchase_price = Decimal("31000")
        self.product.discount_percent = Decimal("5.00")
        self.product.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.barcode, original)

    def test_barcode_png_and_lookup(self):
        png = render_barcode_png(self.product.barcode)
        self.assertGreater(len(png), 100)
        self.assertEqual(get_product_by_barcode(self.product.barcode).pk, self.product.pk)
        with self.assertRaises(BarcodeLookupError):
            get_product_by_barcode("UNKNOWN")

    def test_staff_can_print_and_lookup(self):
        self.client.login(username="pm", password="pass12345")
        response = self.client.get(reverse("products:barcode_png", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        lookup = self.client.get(reverse("products:lookup"), {"barcode": self.product.barcode})
        self.assertEqual(lookup.status_code, 200)
        self.assertTrue(lookup.json()["ok"])

    def test_regenerate_requires_confirmation(self):
        self.client.login(username="pm", password="pass12345")
        old = self.product.barcode
        denied = self.client.post(reverse("products:barcode_regenerate", args=[self.product.pk]))
        self.assertEqual(denied.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.barcode, old)
        ok = self.client.post(
            reverse("products:barcode_regenerate", args=[self.product.pk]), {"confirm": "1"}
        )
        self.assertEqual(ok.status_code, 302)
        self.product.refresh_from_db()
        self.assertNotEqual(self.product.barcode, old)


class FifoAccountingTests(TestCase):
    def setUp(self):
        self.warehouse, self.category, self.vendor, self.product = build_catalog()
        self.staff = User.objects.create_user(
            username="acc",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.ACCOUNTING, MODULES.GRN, MODULES.ORDERS],
        )
        self.customer = User.objects.create_user(
            username="buyer",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="buyer@example.com",
        )
        Address.objects.create(
            user=self.customer,
            full_name="Buyer",
            phone="03001112222",
            address="Street",
            city="Lahore",
            is_default=True,
        )
        self.method = PaymentMethod.objects.get(code=PaymentMethod.Code.COD)
        self.product.selling_price = Decimal("1500.00")
        self.product.purchase_price = Decimal("1000.00")
        self.product.discount_percent = Decimal("10.00")
        self.product.save()

    def _grn(self, qty, rate):
        grn = GRN.objects.create(vendor=self.vendor, warehouse=self.warehouse, received_by=self.staff)
        GRNItem.objects.create(grn=grn, product=self.product, quantity=qty, purchase_rate=Decimal(rate))
        approve_grn(grn, self.staff)
        return grn

    def test_grn_creates_cost_layer_and_payable(self):
        grn = self._grn(100, "1000.00")
        layer = InventoryCostLayer.objects.get(grn=grn)
        self.assertEqual(layer.purchase_rate, Decimal("1000.00"))
        self.assertEqual(layer.remaining_qty, 100)
        self.assertTrue(AccountingPosting.objects.filter(event_key=f"grn_approved:{grn.pk}").exists())
        with self.assertRaises(GRNError):
            approve_grn(grn, self.staff)
        self.product.purchase_price = Decimal("1200.00")
        self.product.save()
        layer.refresh_from_db()
        self.assertEqual(layer.purchase_rate, Decimal("1000.00"))

    def test_fifo_cogs_across_layers(self):
        self._grn(100, "1000.00")
        self._grn(50, "1200.00")
        uses_needed = 120
        from apps.inventory.costing import consume_fifo

        uses = consume_fifo(self.product, self.warehouse, uses_needed, reference="TEST-SALE")
        total = sum((row.amount for row in uses), Decimal("0.00"))
        self.assertEqual(total, Decimal("124000.00"))
        self.assertEqual(layer_value(self.product, self.warehouse), Decimal("36000.00"))

    def test_sale_posts_cogs_and_payment_posts_cash(self):
        self._grn(10, "1000.00")
        CartItem.objects.create(user=self.customer, product=self.product, quantity=2)
        address = self.customer.addresses.first()
        order = place_order(
            request=make_request(self.customer),
            billing_address=address,
            shipping_address=address,
            payment_method=self.method,
        )
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.cogs_total, Decimal("0.00"))
        change_order_status(order, Order.Status.CONFIRMED, user=self.staff)
        order.refresh_from_db()
        self.assertEqual(order.cogs_total, Decimal("2000.00"))
        item = order.items.get()
        self.assertEqual(item.catalog_discount, Decimal("300.00"))
        self.assertEqual(order.grand_total, Decimal("2850.00"))  # 2700 + 150 shipping if TAX 0
        self.assertTrue(AccountingPosting.objects.filter(event_key=f"sale:{order.pk}").exists())
        post_sale_event(order, self.staff)  # idempotent
        self.assertEqual(AccountingPosting.objects.filter(event_key=f"sale:{order.pk}").count(), 1)
        payment = order.payments.first()
        mark_paid(payment, transaction_id="COD-1")
        self.assertTrue(AccountingPosting.objects.filter(event_key=f"payment_paid:{payment.pk}").exists())
        mark_paid(payment, transaction_id="COD-1")
        self.assertEqual(AccountingPosting.objects.filter(event_key=f"payment_paid:{payment.pk}").count(), 1)

    def test_expense_reduces_cash_and_affects_pnl(self):
        expense = Expense.objects.create(
            title="Delivery",
            category=Expense.Category.DELIVERY,
            amount=Decimal("100.00"),
            payment_account="cash",
            created_by=self.staff,
        )
        from apps.accounting.services import post_expense_event

        post_expense_event(expense, self.staff)
        self.assertEqual(account_balance("1000"), Decimal("-100.00"))
        from django.utils import timezone

        totals = period_totals(timezone.localdate(), timezone.localdate())
        self.assertEqual(totals["expenses"], Decimal("100.00"))
        self.assertEqual(totals["net_profit"], Decimal("-100.00"))

    def test_permissions(self):
        other = User.objects.create_user(
            username="ops",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.ORDERS],
        )
        self.client.login(username="ops", password="pass12345")
        self.assertEqual(self.client.get(reverse("accounting:dashboard")).status_code, 403)
        self.client.logout()
        self.client.login(username="buyer", password="pass12345")
        self.assertEqual(self.client.get(reverse("accounting:dashboard")).status_code, 403)
        self.client.logout()
        self.client.login(username="acc", password="pass12345")
        self.assertEqual(self.client.get(reverse("accounting:dashboard")).status_code, 200)

    def test_journals_are_balanced(self):
        self._grn(5, "1000.00")
        for journal in JournalEntry.objects.all():
            self.assertEqual(journal.total_debit, journal.total_credit)

    def test_return_reverses_cogs_for_resellable(self):
        self._grn(10, "1000.00")
        CartItem.objects.create(user=self.customer, product=self.product, quantity=2)
        address = self.customer.addresses.first()
        order = place_order(
            request=make_request(self.customer),
            billing_address=address,
            shipping_address=address,
            payment_method=self.method,
        )
        change_order_status(order, Order.Status.CONFIRMED, user=self.staff)
        change_order_status(order, Order.Status.PROCESSING, user=self.staff)
        change_order_status(order, Order.Status.DELIVERED, user=self.staff)
        ret = ReturnRequest.objects.create(
            order=order, customer=self.customer, reason="size", status=ReturnRequest.Status.APPROVED
        )
        ReturnItem.objects.create(
            return_request=ret,
            order_item=order.items.get(),
            product=self.product,
            quantity=2,
            condition=ReturnItem.Condition.RESELLABLE,
        )
        update_return_status(ret, ReturnRequest.Status.RECEIVED, user=self.staff)
        self.assertTrue(
            AccountingPosting.objects.filter(event_key__startswith=f"return_revenue:{order.pk}:").exists()
        )
        self.assertEqual(layer_value(self.product, self.warehouse), Decimal("10000.00"))

    def test_completed_return_posts_accounting(self):
        self._grn(10, "1000.00")
        CartItem.objects.create(user=self.customer, product=self.product, quantity=2)
        address = self.customer.addresses.first()
        order = place_order(
            request=make_request(self.customer),
            billing_address=address,
            shipping_address=address,
            payment_method=self.method,
        )
        change_order_status(order, Order.Status.CONFIRMED, user=self.staff)
        change_order_status(order, Order.Status.PROCESSING, user=self.staff)
        change_order_status(order, Order.Status.DELIVERED, user=self.staff)
        ret = ReturnRequest.objects.create(
            order=order, customer=self.customer, reason="size", status=ReturnRequest.Status.REQUESTED
        )
        ReturnItem.objects.create(
            return_request=ret,
            order_item=order.items.get(),
            product=self.product,
            quantity=2,
            condition=ReturnItem.Condition.RESELLABLE,
        )
        update_return_status(ret, ReturnRequest.Status.APPROVED, user=self.staff)
        update_return_status(ret, ReturnRequest.Status.COMPLETED, user=self.staff)
        self.assertTrue(
            AccountingPosting.objects.filter(event_key=f"return_revenue:{order.pk}:{ret.pk}").exists()
        )
