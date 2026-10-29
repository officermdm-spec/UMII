from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.categories.models import Category
from apps.inventory.models import Inventory
from apps.inventory.services import available_stock, ensure_inventory, get_default_warehouse
from apps.products.models import Brand, Product, ProductImage
from apps.promotions.models import ProductOffer
from apps.vendors.models import Vendor

User = get_user_model()


class ProductPricingTests(TestCase):
    def setUp(self):
        _, _, _, self.product = build_catalog()
        self.product.selling_price = Decimal("1000.00")
        self.product.discount_percent = Decimal("10.00")
        self.product.save()

    def test_effective_price_applies_discount(self):
        self.assertEqual(self.product.discount_amount, Decimal("100.00"))
        self.assertEqual(self.product.effective_price, Decimal("900.00"))
        self.assertTrue(self.product.has_discount)

    def test_store_detail_shows_discount(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "900")
        self.assertContains(response, "1,000")
        self.assertContains(response, "10%")


class ProductVariantTests(TestCase):
    def setUp(self):
        self.warehouse = get_default_warehouse()
        self.category = Category.objects.create(name="Garments", slug="garments")
        self.vendor = Vendor.objects.create(company_name="UMII Supplier", phone="03000000000")
        self.staff = User.objects.create_user(
            username="variant-staff",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.PRODUCTS],
        )

    def test_staff_can_create_product_with_size_variants(self):
        self.client.login(username="variant-staff", password="pass12345")
        get_response = self.client.get(reverse("products:create"))
        prefix = get_response.context["variant_formset"].prefix
        self.assertNotIn("size", get_response.context["form"].fields)
        self.assertIn("color", get_response.context["form"].fields)
        self.assertIn("size", get_response.context["variant_formset"].empty_form.fields)
        self.assertNotIn("color", get_response.context["variant_formset"].empty_form.fields)
        self.assertNotContains(get_response, 'name="size"')
        self.assertContains(get_response, 'name="color"')
        self.assertContains(get_response, f'name="{prefix}-__prefix__-size"')
        self.assertNotContains(get_response, f'name="{prefix}-__prefix__-color"')
        self.assertContains(get_response, "Add another option")
        self.assertContains(get_response, "Remove option")
        response = self.client.post(
            reverse("products:create"),
            {
                "name": "Everyday Tee",
                "selling_price": "1000.00",
                "purchase_price": "500.00",
                "category": self.category.pk,
                "vendor": self.vendor.pk,
                "brand": "",
                "size": "",
                "color": "Navy",
                "unit": "pcs",
                "discount_percent": "0",
                "min_stock_level": "5",
                "description": "Cotton everyday tee",
                f"{prefix}-TOTAL_FORMS": "1",
                f"{prefix}-INITIAL_FORMS": "0",
                f"{prefix}-MIN_NUM_FORMS": "0",
                f"{prefix}-MAX_NUM_FORMS": "1000",
                f"{prefix}-0-sku": "",
                f"{prefix}-0-size": "S",
                f"{prefix}-0-is_active": "on",
            },
        )
        if response.status_code != 302:
            self.fail(
                f"Product errors: {response.context['form'].errors}; "
                f"variant errors: {response.context['variant_formset'].errors}; "
                f"variant formset errors: {response.context['variant_formset'].non_form_errors()}"
            )
        parent = Product.objects.get(name="Everyday Tee", variant_parent__isnull=True)
        small = Product.objects.get(variant_parent=parent, size="S")
        self.assertEqual(parent.color, "Navy")
        self.assertEqual(small.color, "")
        self.assertTrue(small.sku.startswith(parent.sku))
        self.assertEqual(small.selling_price, parent.selling_price)
        self.assertFalse(Inventory.objects.filter(product=small).exists())

    def test_staff_variant_size_field_is_a_fixed_apparel_dropdown(self):
        from django import forms

        from apps.products.forms import ProductVariantForm

        form = ProductVariantForm()
        self.assertIsInstance(form.fields["size"], forms.ChoiceField)
        self.assertEqual(
            [value for value, _ in form.fields["size"].choices],
            ["", "XS", "S", "M", "L", "XL", "XXL", "XXXL"],
        )

    def test_variant_with_blank_size_is_rejected(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("products:create"),
            {
                "name": "Blank Size Tee",
                "selling_price": "1000.00",
                "purchase_price": "500.00",
                "category": self.category.pk,
                "vendor": self.vendor.pk,
                "brand": "",
                "color": "Navy",
                "unit": "pcs",
                "discount_percent": "0",
                "min_stock_level": "5",
                "description": "",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "",
                "variants-0-size": "",
                "variants-0-is_active": "on",
                "variants-0-DELETE": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name="Blank Size Tee").exists())
        self.assertIn(
            "Enter a size for every variant, or remove the empty option.",
            response.context["variant_formset"].non_form_errors(),
        )

    def test_empty_variant_can_be_removed_before_saving_parent(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("products:create"),
            {
                "name": "Removed Option Tee",
                "selling_price": "1000.00",
                "purchase_price": "500.00",
                "category": self.category.pk,
                "vendor": self.vendor.pk,
                "brand": "",
                "color": "Navy",
                "unit": "pcs",
                "discount_percent": "0",
                "min_stock_level": "5",
                "description": "",
                "variants-TOTAL_FORMS": "1",
                "variants-INITIAL_FORMS": "0",
                "variants-MIN_NUM_FORMS": "0",
                "variants-MAX_NUM_FORMS": "1000",
                "variants-0-sku": "",
                "variants-0-size": "",
                "variants-0-is_active": "on",
                "variants-0-DELETE": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        parent = Product.objects.get(name="Removed Option Tee", variant_parent__isnull=True)
        self.assertFalse(parent.variants.exists())

    def test_existing_variant_cannot_be_updated_with_blank_size(self):
        parent = Product.objects.create(
            name="Everyday Tee",
            sku="TEE-BASE-EDIT",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("500.00"),
            category=self.category,
            vendor=self.vendor,
            color="Navy",
        )
        variant = Product.objects.create(
            name=parent.name,
            sku="TEE-M-EDIT",
            selling_price=parent.selling_price,
            purchase_price=parent.purchase_price,
            category=parent.category,
            vendor=parent.vendor,
            variant_parent=parent,
            size="Medium",
        )
        from apps.products.forms import ProductForm

        form = ProductForm(
            data={
                "name": parent.name,
                "selling_price": "1000.00",
                "purchase_price": "500.00",
                "category": self.category.pk,
                "vendor": self.vendor.pk,
                "brand": "",
                "size": "",
                "unit": "pcs",
                "discount_percent": "0",
                "min_stock_level": "5",
                "description": "",
            },
            instance=variant,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Enter a size for this product variant.", form.errors["size"])

    def test_customer_selects_size_and_cart_uses_variant_stock(self):
        parent = Product.objects.create(
            name="Everyday Tee",
            sku="TEE-BASE",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("500.00"),
            category=self.category,
            vendor=self.vendor,
            color="Navy",
        )
        small = Product.objects.create(
            name=parent.name,
            sku="TEE-S",
            selling_price=parent.selling_price,
            purchase_price=parent.purchase_price,
            category=parent.category,
            vendor=parent.vendor,
            variant_parent=parent,
            size="Small",
        )
        ensure_inventory(small, self.warehouse)
        from apps.inventory.models import StockTransaction
        from apps.inventory.services import record_stock_transaction

        record_stock_transaction(
            product=small,
            warehouse=self.warehouse,
            quantity=4,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference="TEE-S-OPEN",
        )
        out_of_stock = Product.objects.create(
            name=parent.name,
            sku="TEE-L",
            selling_price=parent.selling_price,
            purchase_price=parent.purchase_price,
            category=parent.category,
            vendor=parent.vendor,
            variant_parent=parent,
            size="Large",
        )

        detail = self.client.get(parent.get_absolute_url())
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Small")
        self.assertContains(detail, "4 available")
        self.assertContains(detail, 'type="radio"')
        self.assertContains(detail, f'value="{small.pk}"')
        self.assertNotContains(detail, f'value="{out_of_stock.pk}"')
        self.assertNotContains(detail, "<select")
        self.assertContains(detail, "Navy")
        self.assertContains(detail, "pcs")
        self.assertNotContains(detail, "Large")
        self.assertNotContains(detail, "Choose size / color")

        missing_size = self.client.post(
            reverse("orders_cart:add", args=[parent.pk]), {"quantity": 1}
        )
        self.assertEqual(missing_size.status_code, 302)
        self.assertNotIn(str(small.pk), self.client.session.get("cart", {}))

        unavailable_size = self.client.post(
            reverse("orders_cart:add", args=[parent.pk]),
            {"quantity": 1, "variant_id": str(out_of_stock.pk)},
        )
        self.assertEqual(unavailable_size.status_code, 302)
        self.assertNotIn(str(out_of_stock.pk), self.client.session.get("cart", {}))

        added = self.client.post(
            reverse("orders_cart:add", args=[parent.pk]),
            {"quantity": 2, "variant_id": str(small.pk)},
        )
        self.assertEqual(added.status_code, 302)
        self.assertEqual(self.client.session["cart"][str(small.pk)], 2)
        cart = self.client.get(reverse("orders_cart:cart"))
        self.assertContains(cart, "Size: Small")
        self.assertContains(cart, "Color: Navy")

    def test_parent_product_offers_apply_to_its_size_variants(self):
        parent = Product.objects.create(
            name="Everyday Tee",
            sku="TEE-PROMO",
            selling_price=Decimal("1000.00"),
            purchase_price=Decimal("500.00"),
            category=self.category,
        )
        variant = Product.objects.create(
            name=parent.name,
            sku="TEE-PROMO-M",
            selling_price=parent.selling_price,
            purchase_price=parent.purchase_price,
            category=parent.category,
            variant_parent=parent,
            size="Medium",
        )
        now = timezone.now()
        offer = ProductOffer.objects.create(
            name="Tee sale",
            offer_type=ProductOffer.OfferType.PERCENTAGE,
            value=Decimal("10.00"),
            start_date=now - timedelta(hours=1),
            end_date=now + timedelta(hours=1),
            is_active=True,
        )
        offer.products.add(parent)
        self.assertEqual(variant.effective_price, Decimal("900.00"))

class ProductImageTests(TestCase):
    def setUp(self):
        _, category, vendor, _ = build_catalog()
        self.staff = User.objects.create_user(
            username="pm",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.PRODUCTS],
        )
        self.product = Product.objects.create(
            name="Gallery Item",
            sku="GAL-001",
            selling_price=Decimal("500.00"),
            purchase_price=Decimal("300.00"),
            category=category,
            vendor=vendor,
        )
        ensure_inventory(self.product, get_default_warehouse())

    def test_staff_can_upload_multiple_gallery_images(self):
        self.client.login(username="pm", password="pass12345")
        img1 = SimpleUploadedFile("a.jpg", b"fake-image-1", content_type="image/jpeg")
        img2 = SimpleUploadedFile("b.jpg", b"fake-image-2", content_type="image/jpeg")
        response = self.client.post(
            reverse("products:update", args=[self.product.pk]),
            {
                "name": self.product.name,
                "selling_price": "500.00",
                "purchase_price": "300.00",
                "category": self.product.category_id,
                "vendor": self.product.vendor_id,
                "brand": "",
                "size": "",
                "color": "",
                "unit": "pcs",
                "discount_percent": "0",
                "min_stock_level": "5",
                "description": "",
                "gallery": [img1, img2],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.images.count(), 2)
        self.assertTrue(self.product.image)

    def test_cover_image_falls_back_to_gallery(self):
        ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("c.jpg", b"fake-image-3", content_type="image/jpeg"),
            sort_order=0,
        )
        self.product.image = None
        self.product.save(update_fields=["image"])
        self.assertTrue(self.product.cover_image)
        response = self.client.get(reverse("store:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.cover_image.url)

    def test_cover_image_skips_missing_main_file(self):
        ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("g.webp", b"gallery-bytes", content_type="image/webp"),
            sort_order=0,
        )
        self.product.image = "products/main/missing.webp"
        self.product.save(update_fields=["image"])
        self.assertTrue(self.product.cover_image)
        self.assertIn("gallery", self.product.cover_image.name)


class BrandAssetTests(TestCase):
    def test_logo_and_tab_icon_are_packaged(self):
        from django.contrib.staticfiles import finders

        self.assertTrue(finders.find("brand/logo.png"))
        self.assertTrue(finders.find("brand/favicon.png"))
        self.assertTrue(finders.find("brand/favicon.ico"))

    def test_main_path_can_use_gallery_file(self):
        from pathlib import Path

        from django.conf import settings

        from config.storage import resolve_public_media

        gallery = Path(settings.MEDIA_ROOT) / "products" / "gallery"
        gallery.mkdir(parents=True, exist_ok=True)
        target = gallery / "path-lock.webp"
        target.write_bytes(b"webp-bytes")
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        self.assertEqual(
            resolve_public_media("products/main/path-lock.webp"),
            "products/gallery/path-lock.webp",
        )

    def test_home_renders_logo_and_favicon(self):
        response = self.client.get(reverse("store:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "brand/logo.png")
        self.assertContains(response, "brand/favicon")


class ProductImageStorageTests(SimpleTestCase):
    def test_cover_image_accepts_remote_storage_path_without_local_copy(self):
        image = SimpleNamespace(
            name="products/gallery/remote-image.webp",
            storage=object(),
        )
        self.assertIs(Product()._usable_image(image), image)

    def test_gallery_image_with_remote_storage_is_not_filtered_out(self):
        field = ProductImage._meta.get_field("image")
        with patch.object(field, "storage", object()):
            image = ProductImage(image="products/gallery/remote-image.webp")
            self.assertTrue(image.file_exists)


class InventoryGuardTests(TestCase):
    def setUp(self):
        self.warehouse, _, _, self.product = build_catalog()

    def test_new_product_gets_inventory_row_via_ensure(self):
        inv = ensure_inventory(self.product, self.warehouse)
        self.assertIsInstance(inv, Inventory)
        self.assertEqual(available_stock(self.product, self.warehouse), inv.available_stock)

    def test_staff_product_create_does_not_seed_main_inventory(self):
        staff = User.objects.create_user(
            username="pm2",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.PRODUCTS],
        )
        self.client.login(username="pm2", password="pass12345")
        response = self.client.post(
            reverse("products:create"),
            {
                "name": "Only Lahore Item",
                "selling_price": "100.00",
                "purchase_price": "60.00",
                "category": self.product.category_id,
                "vendor": self.product.vendor_id,
                "brand": "",
                "size": "",
                "color": "",
                "unit": "pcs",
                "discount_percent": "0",
                "min_stock_level": "5",
                "description": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = Product.objects.get(name="Only Lahore Item")
        self.assertFalse(Inventory.objects.filter(product=created).exists())


class BrandStaffViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="brandstaff",
            password="pass12345",
            user_type=User.UserType.STAFF,
            is_staff=True,
            allowed_modules=[MODULES.BRANDS],
        )
        self.client.login(username="brandstaff", password="pass12345")

    def test_staff_can_create_brand(self):
        response = self.client.post(
            reverse("products:brand_create"),
            {"name": "Nurpur", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 302)
        brand = Brand.objects.get(name="Nurpur")
        self.assertEqual(brand.slug, "nurpur")
        listing = self.client.get(reverse("products:brand_list"))
        self.assertContains(listing, "Nurpur")
