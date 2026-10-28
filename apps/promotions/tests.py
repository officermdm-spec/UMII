from datetime import timedelta
from decimal import Decimal

from django import forms
from django.test import TestCase
from django.utils import timezone

from apps.accounts.tests import build_catalog
from apps.promotions.models import ProductOffer, Promotion
from apps.promotions.services import PromotionError, validate_promotion


class PromotionTests(TestCase):
    def setUp(self):
        _, _, _, self.product = build_catalog()
        now = timezone.now()
        self.promo = Promotion.objects.create(
            name="Ten off",
            code="SAVE10",
            discount_type=Promotion.DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            apply_to=Promotion.ApplyTo.ALL,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1),
            min_order_amount=Decimal("1000.00"),
            max_discount=Decimal("2000.00"),
            usage_limit=5,
            is_active=True,
        )

    def test_valid_coupon_applies(self):
        items = [{"product": self.product, "quantity": 1, "line_total": Decimal("45000")}]
        discount = validate_promotion(self.promo, None, items, Decimal("45000"))
        self.assertEqual(discount, Decimal("2000.00"))

    def test_expired_coupon_rejected(self):
        self.promo.end_date = timezone.now() - timedelta(hours=1)
        self.promo.save()
        with self.assertRaises(PromotionError):
            validate_promotion(self.promo, None, [], Decimal("5000"))

    def test_customer_cannot_reuse_coupon(self):
        from django.contrib.auth import get_user_model

        from apps.promotions.models import PromotionUsage
        from apps.orders.models import Order

        User = get_user_model()
        user = User.objects.create_user(
            username="promo-user",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="promo@example.com",
        )
        order = Order.objects.create(
            customer=user,
            billing_full_name="A",
            billing_phone="1",
            billing_address="X",
            billing_city="Y",
            shipping_full_name="A",
            shipping_phone="1",
            shipping_address="X",
            shipping_city="Y",
            payment_method_code="cod",
            grand_total=Decimal("100.00"),
        )
        PromotionUsage.objects.create(promotion=self.promo, customer=user, order=order)
        items = [{"product": self.product, "quantity": 1, "line_total": Decimal("45000")}]
        with self.assertRaises(PromotionError):
            validate_promotion(self.promo, user, items, Decimal("45000"))

    def test_simple_form_saves_home_coupon(self):
        from apps.promotions.forms import PromotionForm

        now = timezone.now()
        form = PromotionForm(
            data={
                "name": "Home sale",
                "code": "home10",
                "discount_type": "percentage",
                "value": "10",
                "min_order_amount": "0",
                "start_date": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "end_date": (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M"),
                "is_active": "on",
                "show_on_website": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        promo = form.save()
        self.assertEqual(promo.code, "HOME10")
        self.assertEqual(promo.discount_type, Promotion.DiscountType.PERCENTAGE)
        self.assertEqual(promo.apply_to, Promotion.ApplyTo.ALL)
        from apps.promotions.services import live_promotions

        self.assertIn(promo, list(live_promotions()))

    def test_percent_applies_only_to_selected_products(self):
        from apps.products.models import Product
        from apps.promotions.services import allocate_coupon_discounts

        other = Product.objects.create(
            name="Case",
            sku="ELE-002",
            selling_price=Decimal("2000.00"),
            purchase_price=Decimal("800.00"),
            category=self.product.category,
            vendor=self.product.vendor,
        )
        skipped = Product.objects.create(
            name="Cable",
            sku="ELE-003",
            selling_price=Decimal("5000.00"),
            purchase_price=Decimal("1000.00"),
            category=self.product.category,
            vendor=self.product.vendor,
        )
        self.promo.apply_to = Promotion.ApplyTo.PRODUCT
        self.promo.min_order_amount = Decimal("0.00")
        self.promo.max_discount = None
        self.promo.save()
        self.promo.products.set([self.product, other])
        items = [
            {"product": self.product, "quantity": 1, "line_total": Decimal("1000.00")},
            {"product": other, "quantity": 1, "line_total": Decimal("2000.00")},
            {"product": skipped, "quantity": 1, "line_total": Decimal("5000.00")},
        ]
        amounts = allocate_coupon_discounts(self.promo, items, Decimal("8000.00"))
        self.assertEqual(amounts, [Decimal("100.00"), Decimal("200.00"), Decimal("0.00")])
        self.assertEqual(sum(amounts), Decimal("300.00"))

    def test_ticked_products_win_even_if_apply_to_is_all(self):
        from apps.products.models import Product
        from apps.promotions.services import allocate_coupon_discounts

        skipped = Product.objects.create(
            name="NURPUR BUTTER 100 GM",
            sku="GRO-001",
            selling_price=Decimal("500.00"),
            purchase_price=Decimal("400.00"),
            category=self.product.category,
            vendor=self.product.vendor,
        )
        self.promo.apply_to = Promotion.ApplyTo.ALL
        self.promo.min_order_amount = Decimal("0.00")
        self.promo.max_discount = None
        self.promo.save()
        self.promo.products.set([self.product])
        items = [
            {"product": self.product, "quantity": 1, "line_total": Decimal("1000.00")},
            {"product": skipped, "quantity": 1, "line_total": Decimal("500.00")},
        ]
        amounts = allocate_coupon_discounts(self.promo, items, Decimal("1500.00"))
        self.assertEqual(amounts, [Decimal("100.00"), Decimal("0.00")])

    def test_form_saves_selected_products(self):
        from apps.inventory.services import ensure_inventory, get_default_warehouse
        from apps.promotions.forms import PromotionForm

        ensure_inventory(self.product, get_default_warehouse())
        now = timezone.now()
        form = PromotionForm(
            data={
                "name": "Phone only",
                "code": "phone10",
                "discount_type": "percentage",
                "value": "10",
                "min_order_amount": "0",
                "products": [self.product.pk],
                "start_date": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "end_date": (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M"),
                "is_active": "on",
                "show_on_website": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        promo = form.save()
        self.assertEqual(promo.apply_to, Promotion.ApplyTo.PRODUCT)
        self.assertEqual(list(promo.products.all()), [self.product])

    def test_staff_can_delete_coupon(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        from apps.accounts.permissions import MODULES

        User = get_user_model()
        User.objects.create_user(
            username="promo-staff",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.PROMOTIONS],
            is_staff=True,
        )
        self.client.login(username="promo-staff", password="pass12345")
        listing = self.client.get(reverse("promotions:list"))
        self.assertContains(listing, reverse("promotions:delete", args=[self.promo.pk]))
        response = self.client.post(reverse("promotions:delete", args=[self.promo.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Promotion.objects.filter(pk=self.promo.pk).exists())


class PromotionProductChoiceTests(TestCase):
    def setUp(self):
        from apps.categories.models import Category
        from apps.products.models import Product
        from apps.vendors.models import Vendor

        category = Category.objects.create(name="Electronics", slug="electronics")
        vendor = Vendor.objects.create(company_name="Acme", phone="03001111111")
        self.product = Product.objects.create(
            name="Demo phone",
            sku="ELE-101",
            selling_price=Decimal("100.00"),
            purchase_price=Decimal("40.00"),
            category=category,
            vendor=vendor,
        )
        self.inactive_product = Product.objects.create(
            name="Inactive phone",
            sku="ELE-102",
            selling_price=Decimal("100.00"),
            purchase_price=Decimal("40.00"),
            category=category,
            vendor=vendor,
            is_active=False,
        )

    def test_coupon_and_offer_dropdowns_list_active_products_without_inventory(self):
        from apps.promotions.forms import ProductOfferForm, PromotionForm

        for form in (PromotionForm(), ProductOfferForm()):
            with self.subTest(form=form.__class__.__name__):
                choices = form.fields["products"]
                product_ids = {product.pk for product in choices.queryset}
                self.assertIn(self.product.pk, product_ids)
                self.assertNotIn(self.inactive_product.pk, product_ids)
                self.assertIsInstance(choices.widget, forms.SelectMultiple)
                self.assertEqual(choices.widget.attrs["size"], 1)

    def test_offer_type_form_fields_match_selected_discount_type(self):
        from apps.promotions.forms import ProductOfferForm

        now = timezone.now()
        common_data = {
            "name": "Test offer",
            "products": [str(self.product.pk)],
            "start_date": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "end_date": (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
            "show_on_website": "on",
        }

        percentage_form = ProductOfferForm(
            data={**common_data, "offer_type": "percentage", "value": "20"}
        )
        self.assertTrue(percentage_form.is_valid(), percentage_form.errors)

        fixed_form = ProductOfferForm(
            data={**common_data, "offer_type": "fixed", "value": "500"}
        )
        self.assertTrue(fixed_form.is_valid(), fixed_form.errors)

        bxgy_form = ProductOfferForm(
            data={
                **common_data,
                "offer_type": "buy_x_get_y",
                "buy_qty": "2",
                "get_qty": "1",
            }
        )
        self.assertTrue(bxgy_form.is_valid(), bxgy_form.errors)
        offer = bxgy_form.save()
        self.assertEqual(offer.value, Decimal("0.00"))

    def test_offer_form_renders_searchable_product_picker(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        from django.template.loader import render_to_string

        from apps.promotions.forms import ProductOfferForm

        request = RequestFactory().get("/staff/promotions/offers/add/")
        request.user = AnonymousUser()
        request.session = {}
        form = ProductOfferForm(
            initial={
                "offer_type": ProductOffer.OfferType.BUY_X_GET_Y,
                "products": [self.product.pk],
            }
        )
        html = render_to_string(
            "staff/promotions/offer_form.html",
            {"form": form, "object": None},
            request=request,
        )

        self.assertIn('data-product-picker', html)
        self.assertIn('data-product-search', html)
        self.assertIn(self.product.name, html)
        self.assertIn('value="{}"'.format(self.product.pk), html)
        self.assertIn('id="offer-bxgy-wrap" class="grid', html)


class CouponListUiTests(TestCase):
    def test_coupon_list_uses_promotions_table_design(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        from apps.accounts.permissions import MODULES
        from apps.categories.models import Category
        from apps.products.models import Product
        from apps.vendors.models import Vendor

        category = Category.objects.create(name="Electronics", slug="electronics")
        vendor = Vendor.objects.create(company_name="Acme", phone="03001111111")
        product = Product.objects.create(
            name="Demo phone",
            sku="ELE-201",
            selling_price=Decimal("100.00"),
            purchase_price=Decimal("40.00"),
            category=category,
            vendor=vendor,
        )
        now = timezone.now()
        promotion = Promotion.objects.create(
            name="Summer deal",
            code="SUMMER10",
            discount_type=Promotion.DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            start_date=now - timedelta(hours=1),
            end_date=now + timedelta(days=7),
        )
        promotion.products.add(product)

        user = get_user_model().objects.create_user(
            username="coupon-list-staff",
            password="test-pass-12345",
            user_type=get_user_model().UserType.STAFF,
            allowed_modules=[MODULES.PROMOTIONS],
        )
        self.client.force_login(user)
        response = self.client.get(reverse("promotions:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SUMMER10")
        self.assertContains(response, "Demo phone")
        self.assertContains(response, "Products")
        self.assertContains(response, "Unlimited")


class ProductOfferAndQuoteTests(TestCase):
    def setUp(self):
        _, self.category, self.vendor, self.product = build_catalog()
        now = timezone.now()
        self.offer = ProductOffer.objects.create(
            name="Summer Sale",
            offer_type=ProductOffer.OfferType.PERCENTAGE,
            value=Decimal("20.00"),
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=7),
            is_active=True,
            show_on_website=True,
        )
        self.offer.products.add(self.product)
        self.coupon = Promotion.objects.create(
            name="SAVE10",
            code="SAVE10",
            discount_type=Promotion.DiscountType.PERCENTAGE,
            value=Decimal("10.00"),
            apply_to=Promotion.ApplyTo.ALL,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=7),
            min_order_amount=Decimal("0.00"),
            is_active=True,
            show_on_website=True,
        )

    def test_product_offer_reduces_unit_price(self):
        from apps.promotions.services import unit_price_for

        self.assertEqual(unit_price_for(self.product), Decimal("36000.00"))
        self.assertTrue(self.product.has_discount)
        self.assertIn("20%", self.product.offer_badge)

    def test_best_offer_wins_when_multiple_are_live(self):
        from apps.promotions.services import unit_price_for

        weaker = ProductOffer.objects.create(
            name="Small cut",
            offer_type=ProductOffer.OfferType.PERCENTAGE,
            value=Decimal("5.00"),
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=7),
            is_active=True,
        )
        weaker.products.add(self.product)
        self.assertEqual(unit_price_for(self.product), Decimal("36000.00"))

    def test_expired_offer_is_ignored(self):
        from apps.promotions.services import unit_price_for

        self.offer.end_date = timezone.now() - timedelta(hours=1)
        self.offer.save()
        self.assertEqual(unit_price_for(self.product), self.product.selling_price)

    def test_quote_does_not_stack_coupon_on_offer_by_default(self):
        from apps.promotions.services import quote_promotions

        items = [{"product": self.product, "quantity": 1}]
        with self.assertRaises(PromotionError):
            quote_promotions(items, coupon_code="SAVE10", allow_stack=False)

    def test_quote_can_stack_when_enabled(self):
        from apps.promotions.services import quote_promotions

        items = [{"product": self.product, "quantity": 1}]
        quote = quote_promotions(items, coupon_code="SAVE10", allow_stack=True)
        self.assertEqual(quote["product_discount"], Decimal("9000.00"))
        self.assertEqual(quote["coupon_discount"], Decimal("3600.00"))
        self.assertEqual(quote["merchandise_total"], Decimal("32400.00"))

    def test_fixed_coupon_and_min_order(self):
        from apps.promotions.services import quote_promotions

        self.offer.delete()
        self.coupon.discount_type = Promotion.DiscountType.FIXED
        self.coupon.value = Decimal("500.00")
        self.coupon.min_order_amount = Decimal("5000.00")
        self.coupon.save()
        items = [{"product": self.product, "quantity": 1}]
        quote = quote_promotions(items, coupon_code="SAVE10")
        self.assertEqual(quote["coupon_discount"], Decimal("500.00"))
        self.coupon.min_order_amount = Decimal("50000.00")
        self.coupon.save()
        with self.assertRaises(PromotionError):
            quote_promotions(items, coupon_code="SAVE10")

    def test_buy_x_get_y_makes_third_item_free(self):
        from apps.promotions.services import quote_promotions

        self.offer.offer_type = ProductOffer.OfferType.BUY_X_GET_Y
        self.offer.buy_qty = 2
        self.offer.get_qty = 1
        self.offer.value = Decimal("0.00")
        self.offer.save()
        items = [{"product": self.product, "quantity": 3}]
        quote = quote_promotions(items, coupon_code=None)
        self.assertEqual(quote["merchandise_total"], Decimal("90000.00"))
        self.assertEqual(quote["product_discount"], Decimal("45000.00"))

    def test_totals_never_go_negative(self):
        from apps.promotions.services import quote_promotions

        self.offer.delete()
        self.coupon.discount_type = Promotion.DiscountType.FIXED
        self.coupon.value = Decimal("999999.00")
        self.coupon.save()
        items = [{"product": self.product, "quantity": 1}]
        quote = quote_promotions(items, coupon_code="SAVE10")
        self.assertGreaterEqual(quote["merchandise_total"], Decimal("0.00"))

    def test_staff_offer_list(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        from apps.accounts.permissions import MODULES

        User = get_user_model()
        User.objects.create_user(
            username="offer-staff",
            password="pass12345",
            user_type=User.UserType.STAFF,
            allowed_modules=[MODULES.PROMOTIONS],
            is_staff=True,
        )
        self.client.login(username="offer-staff", password="pass12345")
        response = self.client.get(reverse("promotions:offer_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summer Sale")

    def test_cancel_restores_coupon_usage(self):
        from django.contrib.auth import get_user_model

        from apps.orders.models import Order
        from apps.promotions.models import PromotionUsage
        from apps.promotions.services import restore_coupon_usage

        User = get_user_model()
        user = User.objects.create_user(
            username="coupon-user",
            password="pass12345",
            user_type=User.UserType.CUSTOMER,
            email="cu@example.com",
        )
        order = Order.objects.create(
            customer=user,
            billing_full_name="A",
            billing_phone="1",
            billing_address="X",
            billing_city="Y",
            shipping_full_name="A",
            shipping_phone="1",
            shipping_address="X",
            shipping_city="Y",
            payment_method_code="cod",
            grand_total=Decimal("100.00"),
            coupon_code="SAVE10",
        )
        PromotionUsage.objects.create(promotion=self.coupon, customer=user, order=order)
        Promotion.objects.filter(pk=self.coupon.pk).update(used_count=1)
        restore_coupon_usage(order)
        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 0)
        self.assertFalse(PromotionUsage.objects.filter(order=order).exists())
