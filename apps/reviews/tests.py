from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.tests import build_catalog
from apps.inventory.models import StockTransaction
from apps.inventory.services import record_stock_transaction
from apps.orders.models import Order, OrderItem
from apps.reviews.models import Feedback, Review

User = get_user_model()


class ReviewVerificationTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()
        record_stock_transaction(
            product=self.product,
            warehouse=self.warehouse,
            quantity=5,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="OPEN",
        )
        self.customer = User.objects.create_user(
            username="buyer",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="buyer@example.com",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            billing_full_name="B",
            billing_phone="1",
            billing_address="A",
            billing_city="C",
            shipping_full_name="B",
            shipping_phone="1",
            shipping_address="A",
            shipping_city="C",
            payment_method_code="cod",
            status=Order.Status.DELIVERED,
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            sku=self.product.sku,
            product_name=self.product.name,
            quantity=1,
            unit_price=self.product.selling_price,
            total=self.product.selling_price,
        )

    def test_verified_buyer_can_review(self):
        self.client.login(username="buyer", password="pass12345")
        response = self.client.post(
            reverse("reviews_customer:create", args=[self.order.pk, self.item.pk]),
            {"rating": 5, "comment": "Great phone"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Review.objects.count(), 1)

    def test_non_buyer_cannot_review_foreign_order(self):
        User.objects.create_user(
            username="stranger",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="s@example.com",
        )
        self.client.login(username="stranger", password="pass12345")
        response = self.client.get(
            reverse("reviews_customer:create", args=[self.order.pk, self.item.pk])
        )
        self.assertEqual(response.status_code, 404)


class FeedbackFlowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="buyer2",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="buyer2@example.com",
        )

    def test_customer_can_send_feedback(self):
        self.client.login(username="buyer2", password="pass12345")
        response = self.client.post(
            reverse("reviews_customer:feedback"),
            {
                "topic": Feedback.Topic.ORDER,
                "rating": 4,
                "subject": "Delivery was late",
                "message": "Please improve timing.",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = Feedback.objects.get()
        self.assertEqual(item.topic, Feedback.Topic.ORDER)
        self.assertEqual(item.status, Feedback.Status.NEW)
