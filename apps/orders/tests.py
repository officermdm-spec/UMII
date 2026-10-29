from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.categories.models import Category
from apps.customers.models import Address
from apps.inventory.models import StockTransaction, Warehouse
from apps.inventory.services import available_stock, record_stock_transaction
from apps.orders.models import CartItem, Order, OrderItem, OrderStatusHistory
from apps.orders.services import OrderError, build_order_tracker, change_order_status, place_order
from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import create_payment_for_order, set_order_payment_status
from apps.products.models import Product
from apps.vendors.models import Vendor

User = get_user_model()


class OrderIsolationTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=10,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        self.customer = User.objects.create_user(
            username="cust1",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="c1@example.com",
        )
        self.other = User.objects.create_user(
            username="cust2",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="c2@example.com",
        )
        self.address = Address.objects.create(
            user=self.customer,
            full_name="Cust One",
            phone="03001230000",
            address="Street 1",
            city="Karachi",
            is_default=True,
        )
        Address.objects.create(
            user=self.other,
            full_name="Cust Two",
            phone="03001230001",
            address="Street 2",
            city="Lahore",
            is_default=True,
        )
        self.method = PaymentMethod.objects.get(code=PaymentMethod.Code.COD)

    def test_customer_cannot_open_another_customers_order(self):
        order = Order.objects.create(
            customer=self.other,
            billing_full_name="X",
            billing_phone="1",
            billing_address="A",
            billing_city="C",
            shipping_full_name="X",
            shipping_phone="1",
            shipping_address="A",
            shipping_city="C",
            payment_method_code="cod",
            grand_total=Decimal("10.00"),
        )
        self.client.login(username="cust1", password="pass12345")
        response = self.client.get(reverse("orders_customer:detail", args=[order.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cart_rejects_external_next_redirect(self):
        self.client.login(username="cust1", password="pass12345")
        response = self.client.post(
            reverse("orders_cart:add", args=[self.product.pk]),
            {"quantity": 1, "next": "https://evil.example/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response["Location"])

    def test_customer_cannot_open_another_customers_invoice(self):
        order = Order.objects.create(
            customer=self.other,
            billing_full_name="X",
            billing_phone="1",
            billing_address="A",
            billing_city="C",
            shipping_full_name="X",
            shipping_phone="1",
            shipping_address="A",
            shipping_city="C",
            payment_method_code="cod",
            grand_total=Decimal("10.00"),
            invoice_number="INV-SECRET-1",
        )
        self.client.login(username="cust1", password="pass12345")
        response = self.client.get(reverse("orders_customer:invoice", args=[order.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cart_rejects_quantity_above_stock(self):
        self.client.login(username="cust1", password="pass12345")
        response = self.client.post(
            reverse("orders_cart:add", args=[self.product.pk]), {"quantity": 99}
        )
        self.assertEqual(response.status_code, 302)
        follow = self.client.get(reverse("orders_cart:cart"))
        self.assertEqual(follow.context["summary"]["item_count"], 0)


class GuestCheckoutTests(TestCase):
    def setUp(self):
        self.warehouse = Warehouse.objects.create(name="Main", code="MAIN")
        category = Category.objects.create(name="Guest Category", slug="guest-category")
        vendor = Vendor.objects.create(company_name="Guest Supplier", phone="03001111111")
        self.product = Product.objects.create(
            name="Guest Product",
            sku="GUEST-001",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("500.00"),
            category=category,
            vendor=vendor,
        )
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="GUEST-OPEN",
        )
        self.method, _ = PaymentMethod.objects.get_or_create(
            code=PaymentMethod.Code.COD,
            defaults={"name": "Cash on Delivery"},
        )

    def test_guest_checkout_creates_customer_account_and_trackable_order(self):
        self.client.post(
            reverse("orders_cart:add", args=[self.product.pk]),
            {"quantity": 1},
        )

        response = self.client.post(
            reverse("orders_checkout:checkout"),
            {
                "full_name": "Guest Customer",
                "email": "guest@example.com",
                "phone": "03001230000",
                "address": "Street 1",
                "city": "Karachi",
                "area": "Central",
                "postal_code": "74000",
                "payment_method": self.method.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        customer = order.customer
        self.assertEqual(customer.email, "guest@example.com")
        self.assertEqual(customer.user_type, User.UserType.CUSTOMER)
        self.assertFalse(customer.has_usable_password())
        self.assertEqual(order.shipping_full_name, "Guest Customer")
        self.assertEqual(order.shipping_phone, "03001230000")
        self.assertEqual(order.shipping_address, "Street 1")
        self.assertEqual(order.shipping_city, "Karachi")
        self.assertTrue(customer.addresses.filter(is_default=True).exists())
        self.assertIn(order.order_number, response["Location"])

        tracking = self.client.get(response["Location"])
        self.assertEqual(tracking.status_code, 200)
        self.assertContains(tracking, order.order_number)
        self.assertContains(tracking, "Pending")
        self.assertContains(tracking, "Set your password by email")
        self.assertNotContains(tracking, "Street 1")
        self.assertNotContains(tracking, "Guest Customer")

    def test_tracking_rejects_unknown_order_number(self):
        response = self.client.get(
            reverse("orders_customer:track"),
            {"order_number": "ORD-NOT-FOUND"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "We couldn&#x27;t find an order with that number.")

    def test_signed_in_customer_can_still_checkout_with_saved_address(self):
        customer = User.objects.create_user(
            username="saved-customer",
            password="safe-test-password",
            email="saved@example.com",
            user_type=User.UserType.CUSTOMER,
        )
        address = Address.objects.create(
            user=customer,
            full_name="Saved Customer",
            phone="03001230001",
            address="Street 2",
            city="Lahore",
            is_default=True,
        )
        CartItem.objects.create(user=customer, product=self.product, quantity=1)
        self.client.login(username="saved-customer", password="safe-test-password")

        checkout = self.client.get(reverse("orders_checkout:checkout"))
        self.assertFalse(checkout.context["guest_checkout"])
        response = self.client.post(
            reverse("orders_checkout:checkout"),
            {
                "billing_address": address.pk,
                "shipping_address": address.pk,
                "same_as_billing": "on",
                "payment_method": self.method.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.customer, customer)
        self.assertEqual(order.shipping_address, "Street 2")


class OrderStatusUpdateTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=20,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        self.customer = User.objects.create_user(
            username="buyer",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="buyer@example.com",
        )
        self.staff = User.objects.create_user(
            username="ops",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.ORDERS, MODULES.PAYMENTS],
        )
        self.method = PaymentMethod.objects.get(code=PaymentMethod.Code.COD)
        self.order = Order.objects.create(
            customer=self.customer,
            billing_full_name="Buyer",
            billing_phone="03001112222",
            billing_address="Street",
            billing_city="Karachi",
            shipping_full_name="Buyer",
            shipping_phone="03001112222",
            shipping_address="Street",
            shipping_city="Karachi",
            payment_method_code=PaymentMethod.Code.COD,
            payment_status=Order.PaymentStatus.COD_PENDING,
            status=Order.Status.PENDING,
            grand_total=Decimal("45000.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            sku=self.product.sku,
            product_name=self.product.name,
            quantity=1,
            unit_price=self.product.selling_price,
            total=self.product.selling_price,
        )
        create_payment_for_order(self.order, self.method, user=self.customer)
        OrderStatusHistory.objects.create(
            order=self.order, status=Order.Status.PENDING, note="seed"
        )

    def test_staff_can_update_order_status(self):
        self.client.login(username="ops", password="pass12345")
        response = self.client.post(
            reverse("orders_staff:status", args=[self.order.pk]),
            {"status": Order.Status.CONFIRMED, "note": "Verified"},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertTrue(
            self.order.status_history.filter(status=Order.Status.CONFIRMED).exists()
        )

    def test_staff_can_update_payment_status(self):
        self.client.login(username="ops", password="pass12345")
        response = self.client.post(
            reverse("orders_staff:payment_status", args=[self.order.pk]),
            {"payment_status": Order.PaymentStatus.PAID, "transaction_id": "COD-1"},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        payment = self.order.payments.first()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.transaction_id, "COD-1")

    def test_customer_sees_order_and_payment_status(self):
        self.client.login(username="buyer", password="pass12345")
        response = self.client.get(reverse("orders_customer:detail", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending")
        self.assertContains(response, "COD Pending")
        self.assertTrue(response.context["can_cancel"])

    def test_customer_can_cancel_pending_order(self):
        self.client.login(username="buyer", password="pass12345")
        response = self.client.post(reverse("orders_customer:cancel", args=[self.order.pk]))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)

    def test_cod_delivery_marks_payment_paid(self):
        change_order_status(self.order, Order.Status.CONFIRMED, user=self.staff)
        change_order_status(self.order, Order.Status.PROCESSING, user=self.staff)
        change_order_status(self.order, Order.Status.DELIVERED, user=self.staff)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.PAID)
        self.assertTrue(self.order.invoice_number)
        self.assertTrue(self.order.invoice_number.startswith("INV-"))

    def test_superuser_skip_to_delivered_still_posts_sale_once(self):
        admin = User.objects.create_superuser("root", "root@example.com", "pass12345")
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=1,
            transaction_type=StockTransaction.Type.RESERVE,
            reference=self.order.order_number,
        )
        change_order_status(self.order, Order.Status.DELIVERED, user=admin)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(
            StockTransaction.objects.filter(
                reference=self.order.order_number, transaction_type=StockTransaction.Type.SALE
            ).count(),
            1,
        )
        change_order_status(self.order, Order.Status.RECEIVED, user=admin)
        self.assertEqual(
            StockTransaction.objects.filter(
                reference=self.order.order_number, transaction_type=StockTransaction.Type.SALE
            ).count(),
            1,
        )

    def test_customer_cannot_cancel_after_confirm(self):
        change_order_status(self.order, Order.Status.CONFIRMED, user=self.staff)
        self.client.login(username="buyer", password="pass12345")
        response = self.client.post(reverse("orders_customer:cancel", args=[self.order.pk]))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        detail = self.client.get(reverse("orders_customer:detail", args=[self.order.pk]))
        self.assertFalse(detail.context["can_cancel"])
        self.assertTrue(detail.context["needs_cancel_contact"])
        self.assertContains(detail, "WhatsApp")
        self.assertNotContains(detail, "In Progress")
        self.assertNotContains(detail, "On Way")

    def test_customer_can_optionally_mark_received(self):
        change_order_status(self.order, Order.Status.CONFIRMED, user=self.staff)
        change_order_status(self.order, Order.Status.PROCESSING, user=self.staff)
        change_order_status(self.order, Order.Status.DELIVERED, user=self.staff)
        self.client.login(username="buyer", password="pass12345")
        response = self.client.post(reverse("orders_customer:received", args=[self.order.pk]))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.RECEIVED)

    def test_invalid_status_transition_rejected(self):
        with self.assertRaises(OrderError):
            change_order_status(self.order, Order.Status.DELIVERED, user=self.staff)

    def test_set_order_payment_status_syncs_payment_row(self):
        set_order_payment_status(self.order, Order.PaymentStatus.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PaymentStatus.FAILED)
        self.assertEqual(self.order.payments.first().status, Payment.Status.FAILED)

    def test_tracker_shows_fulfillment_progress(self):
        tracker = build_order_tracker(self.order)
        self.assertEqual(tracker["mode"], "fulfillment")
        self.assertEqual(tracker["current"], Order.Status.PENDING)
        self.assertEqual(tracker["steps"][0]["state"], "current")
        self.assertEqual(tracker["steps"][1]["state"], "upcoming")

        change_order_status(self.order, Order.Status.CONFIRMED, user=self.staff)
        change_order_status(self.order, Order.Status.PROCESSING, user=self.staff)
        self.order.refresh_from_db()
        tracker = build_order_tracker(self.order)
        self.assertEqual(tracker["current_label"], "Processing")
        keys = [step["key"] for step in tracker["steps"]]
        self.assertNotIn(Order.Status.IN_PROGRESS, keys)
        self.assertNotIn(Order.Status.ON_WAY, keys)
        self.assertEqual(tracker["steps"][2]["state"], "current")
        self.assertGreater(tracker["progress_percent"], 30)

    def test_tracker_cancelled_and_return_modes(self):
        change_order_status(self.order, Order.Status.CANCELLED, user=self.staff)
        tracker = build_order_tracker(self.order)
        self.assertEqual(tracker["mode"], "cancelled")
        self.assertEqual(tracker["steps"][-1]["state"], "cancelled")

        order2 = Order.objects.create(
            customer=self.customer,
            billing_full_name="Buyer",
            billing_phone="03001112222",
            billing_address="Street",
            billing_city="Karachi",
            shipping_full_name="Buyer",
            shipping_phone="03001112222",
            shipping_address="Street",
            shipping_city="Karachi",
            payment_method_code=PaymentMethod.Code.COD,
            payment_status=Order.PaymentStatus.PAID,
            status=Order.Status.DELIVERED,
            grand_total=Decimal("100.00"),
        )
        OrderStatusHistory.objects.create(order=order2, status=Order.Status.DELIVERED)
        change_order_status(order2, Order.Status.RETURN_REQUESTED, user=self.staff)
        tracker = build_order_tracker(order2)
        self.assertEqual(tracker["mode"], "return")
        self.assertEqual(tracker["current"], Order.Status.RETURN_REQUESTED)


class SessionDict(dict):
    modified = False


def make_request(user):
    return type("R", (), {"user": user, "session": SessionDict()})()


class ProductVariantOrderSnapshotTests(TestCase):
    def test_order_keeps_selected_size_snapshot(self):
        warehouse = Warehouse.objects.create(name="Main", code="MAIN")
        category = Category.objects.create(name="Garments", slug="garments")
        parent = Product.objects.create(
            name="Everyday Tee",
            sku="TEE-BASE",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("500.00"),
            category=category,
        )
        variant = Product.objects.create(
            name=parent.name,
            sku="TEE-M",
            selling_price=parent.selling_price,
            purchase_price=parent.purchase_price,
            category=parent.category,
            variant_parent=parent,
            size="Medium",
        )
        customer = User.objects.create_user(
            username="variant-buyer",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
        )
        address = Address.objects.create(
            user=customer,
            full_name="Variant Buyer",
            phone="03000000000",
            address="Street 1",
            city="Karachi",
            is_default=True,
        )
        method, _ = PaymentMethod.objects.get_or_create(
            code=PaymentMethod.Code.COD,
            defaults={"name": "Cash on Delivery"},
        )
        record_stock_transaction(
            product=variant,
            warehouse=warehouse,
            quantity=3,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="TEE-M-OPEN",
        )
        CartItem.objects.create(user=customer, product=variant, quantity=1)
        order = place_order(
            request=make_request(customer),
            billing_address=address,
            shipping_address=address,
            payment_method=method,
        )
        item = order.items.get()
        self.assertEqual(item.product_size, "Medium")
        self.assertEqual(item.sku, "TEE-M")


class WarehouseAwareCartTests(TestCase):
    def setUp(self):
        self.main, _, _, self.product = build_catalog()
        self.lahore = Warehouse.objects.create(name="Lahore", code="LHR", address="Lahore")
        record_stock_transaction(
            product=self.product,
            warehouse=self.lahore,
            quantity=6,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="LHR-OPEN",
        )
        self.customer = User.objects.create_user(
            username="cust-lhr",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="lhr@example.com",
        )
        self.address = Address.objects.create(
            user=self.customer,
            full_name="Cust Lhr",
            phone="03001239999",
            address="Street 9",
            city="Lahore",
            is_default=True,
        )
        self.method = PaymentMethod.objects.get(code=PaymentMethod.Code.COD)
        self.staff = User.objects.create_user(
            username="ops-lhr",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.ORDERS],
        )

    def test_cart_accepts_stock_from_selected_warehouse(self):
        self.assertEqual(available_stock(self.product, self.main), 0)
        self.assertEqual(available_stock(self.product), 6)
        self.client.login(username="cust-lhr", password="pass12345")
        response = self.client.post(
            reverse("orders_cart:add", args=[self.product.pk]), {"quantity": 2}
        )
        self.assertEqual(response.status_code, 302)
        cart = self.client.get(reverse("orders_cart:cart"))
        self.assertEqual(cart.context["summary"]["item_count"], 2)

    def test_place_order_reserves_and_confirms_from_stocked_warehouse(self):
        CartItem.objects.create(user=self.customer, product=self.product, quantity=2)
        order = place_order(
            request=make_request(self.customer),
            billing_address=self.address,
            shipping_address=self.address,
            payment_method=self.method,
        )
        self.assertEqual(order.fulfillment_warehouse, self.lahore)
        self.assertEqual(available_stock(self.product, self.lahore), 4)
        self.assertEqual(available_stock(self.product, self.main), 0)
        self.assertTrue(
            StockTransaction.objects.filter(
                reference=order.order_number,
                transaction_type=StockTransaction.Type.RESERVE,
                warehouse=self.lahore,
            ).exists()
        )
        change_order_status(order, Order.Status.CONFIRMED, user=self.staff)
        change_order_status(order, Order.Status.PROCESSING, user=self.staff)
        order.refresh_from_db()
        tracker = build_order_tracker(order)
        self.assertEqual(tracker["current"], Order.Status.PROCESSING)
        self.assertEqual(tracker["steps"][2]["state"], "current")
        self.assertEqual(
            StockTransaction.objects.filter(
                reference=order.order_number,
                transaction_type=StockTransaction.Type.SALE,
                warehouse=self.lahore,
            ).count(),
            1,
        )
        self.assertFalse(
            StockTransaction.objects.filter(
                reference=order.order_number, warehouse=self.main
            ).exists()
        )
        change_order_status(order, Order.Status.DELIVERED, user=self.staff)
        order.refresh_from_db()
        tracker = build_order_tracker(order)
        self.assertEqual(tracker["current"], Order.Status.DELIVERED)
        self.client.login(username="ops-lhr", password="pass12345")
        detail = self.client.get(reverse("orders_staff:detail", args=[order.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Delivered")
        self.assertEqual(detail.context["tracker"]["current"], Order.Status.DELIVERED)
