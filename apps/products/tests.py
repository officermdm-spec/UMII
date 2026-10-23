from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.permissions import MODULES
from apps.accounts.tests import build_catalog
from apps.inventory.models import Inventory
from apps.inventory.services import available_stock, ensure_inventory, get_default_warehouse
from apps.products.models import Brand, Product, ProductImage
from django.contrib.auth import get_user_model

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
