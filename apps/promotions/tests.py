from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import MODULES
from apps.categories.models import Category
from apps.orders.models import Order, OrderItem
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
        self.assertEqual(self.product.savings_amount, Decimal("200.00"))

    def test_product_detail_shows_live_offer_savings(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "You save")
        self.assertContains(response, "200")

    def test_cart_shows_total_savings_for_live_offer(self):
        session = self.client.session
        session["cart"] = {str(self.product.pk): 2}
        session.save()

        response = self.client.get(reverse("orders_cart:cart"))
        self.assertContains(response, "You save")
        self.assertContains(response, "400")

    def test_homepage_separates_active_website_offers(self):
        response = self.client.get(reverse("store:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Special offers")
        self.assertIn(self.product, response.context["deals"])

        self.offer.show_on_website = False
        self.offer.save(update_fields=["show_on_website"])
        response = self.client.get(reverse("store:home"))
        self.assertNotContains(response, "Special offers")
        self.assertNotIn(self.product, response.context["deals"])

    def test_category_images_and_related_products_show_on_home_and_category_pages(self):
        self.category.image.save(
            "electronics.jpg",
            SimpleUploadedFile(
                "electronics.jpg",
                b"category-image",
                content_type="image/jpeg",
            ),
            save=True,
        )

        home_response = self.client.get(reverse("store:home"))

        self.assertEqual(home_response.status_code, 200)
        category_section = next(
            section
            for section in home_response.context["category_sections"]
            if section.pk == self.category.pk
        )
        self.assertEqual(list(category_section.home_products), [self.product])
        self.assertContains(home_response, self.category.image.url)

        category_response = self.client.get(
            reverse("store:category", args=[self.category.slug])
        )

        self.assertEqual(category_response.status_code, 200)
        self.assertContains(category_response, self.category.image.url)

    def test_homepage_ranks_best_sellers_by_fulfilled_quantity(self):
        User = get_user_model()
        customer = User.objects.create_user(
            username="best-seller-buyer",
            password="pass12345",
        )
        other_product = Product.objects.create(
            name="Other product",
            sku="ELE-102",
            selling_price=Decimal("500.00"),
            purchase_price=Decimal("200.00"),
            category=self.category,
            vendor=self.vendor,
        )

        for product, quantity in ((self.product, 2), (other_product, 5)):
            order = Order.objects.create(
                customer=customer,
                billing_full_name="Buyer",
                billing_phone="03000000000",
                billing_address="Street",
                billing_city="Karachi",
                shipping_full_name="Buyer",
                shipping_phone="03000000000",
                shipping_address="Street",
                shipping_city="Karachi",
                payment_method_code="cod",
                status=Order.Status.DELIVERED,
            )
            OrderItem.objects.create(
                order=order,
                product=product,
                sku=product.sku,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.selling_price,
                total=product.selling_price * quantity,
            )

        response = self.client.get(reverse("store:home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["top_sellers"][0], other_product)

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
