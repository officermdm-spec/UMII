from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.permissions import MODULES
from apps.categories.models import Category
from apps.products.models import Product
from apps.promotions.models import ProductOffer
from apps.promotions.services import quote_product_offers, unit_price_for
from apps.vendors.models import Vendor


class ProductOfferTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Electronics", slug="electronics")
        self.vendor = Vendor.objects.create(company_name="Acme", phone="03001111111")
        self.product = Product.objects.create(
            name="Demo phone",
            sku="ELE-101",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("400.00"),
            category=self.category,
            vendor=self.vendor,
        )
        self.offer = self.create_offer("Summer Sale", "20.00")

    def create_offer(self, name, value):
        now = timezone.now()
        offer = ProductOffer.objects.create(
            name=name,
            offer_type=ProductOffer.OfferType.PERCENTAGE,
            value=Decimal(value),
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=7),
            is_active=True,
        )
        offer.products.add(self.product)
        return offer

    def test_product_offer_reduces_unit_price(self):
        self.assertEqual(unit_price_for(self.product), Decimal("800.00"))
        self.assertTrue(self.product.has_discount)

    def test_best_live_offer_wins(self):
        self.create_offer("Smaller sale", "5.00")
        self.assertEqual(unit_price_for(self.product), Decimal("800.00"))

    def test_expired_offer_is_ignored(self):
        self.offer.end_date = timezone.now() - timedelta(hours=1)
        self.offer.save()
        self.assertEqual(unit_price_for(self.product), self.product.selling_price)

    def test_quote_product_offers_keeps_totals_consistent(self):
        quote = quote_product_offers([{"product": self.product, "quantity": 2}])
        self.assertEqual(quote["list_subtotal"], Decimal("2000.00"))
        self.assertEqual(quote["product_discount"], Decimal("400.00"))
        self.assertEqual(quote["merchandise_total"], Decimal("1600.00"))
        self.assertEqual(quote["items"][0]["line_total"], Decimal("1600.00"))

    def test_buy_x_get_y_discounts_free_units(self):
        self.offer.offer_type = ProductOffer.OfferType.BUY_X_GET_Y
        self.offer.value = Decimal("0.00")
        self.offer.buy_qty = 2
        self.offer.get_qty = 1
        self.offer.save()
        quote = quote_product_offers([{"product": self.product, "quantity": 3}])
        self.assertEqual(quote["merchandise_total"], Decimal("2000.00"))
        self.assertEqual(quote["product_discount"], Decimal("1000.00"))

    def test_coupon_routes_are_removed(self):
        from django.urls import resolve, Resolver404

        with self.assertRaises(Resolver404):
            resolve("/checkout/coupon/apply/")
        with self.assertRaises(Resolver404):
            resolve("/staff/promotions/")

    def test_checkout_form_has_no_coupon_field(self):
        from django.contrib.auth import get_user_model

        from apps.orders.forms import CheckoutForm

        user = get_user_model().objects.create_user(
            username="checkout-user",
            password="test-password",
        )
        self.assertNotIn("coupon_code", CheckoutForm(user=user).fields)

    def test_staff_can_manage_product_offers(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        User = get_user_model()
        staff = User.objects.create_user(
            username="offer-staff",
            password="test-password",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.PROMOTIONS],
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("promotions:offer_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summer Sale")
