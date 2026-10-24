from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify


class Brand(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    sku = models.CharField("Item Code / SKU", max_length=50, unique=True)
    barcode = models.CharField(max_length=32, unique=True, blank=True)
    barcode_image = models.ImageField(upload_to="products/barcodes/", blank=True, null=True)
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))]
    )
    category = models.ForeignKey(
        "categories.Category",
        on_delete=models.PROTECT,
        related_name="products",
    )
    vendor = models.ForeignKey(
        "vendors.Vendor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    variant_parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="variants",
    )
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/main/", blank=True, null=True)
    size = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=30, default="pcs")
    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    stock_quantity = models.IntegerField(default=0)
    min_stock_level = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["sku"]),
            models.Index(fields=["barcode"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["vendor"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["variant_parent", "size", "color"],
                condition=Q(variant_parent__isnull=False),
                name="uniq_product_variant_size_color",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.sku or 'item'}")
        from apps.products.barcode import allocate_unique_barcode

        for _ in range(8):
            if not self.barcode:
                self.barcode = allocate_unique_barcode()
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError as exc:
                if self.pk or "barcode" not in str(exc).lower():
                    raise
                self.barcode = ""
        super().save(*args, **kwargs)

    def __str__(self):
        if self.variant_parent_id:
            details = " / ".join(filter(None, (self.size, self.color)))
            return f"{self.name} — {details} ({self.sku})"
        return f"{self.name} ({self.sku})"

    def get_absolute_url(self):
        product = self.variant_parent or self
        return reverse("store:product_detail", kwargs={"slug": product.slug})

    @property
    def discount_amount(self):
        if self.discount_percent and self.discount_percent > 0:
            return (
                (self.selling_price * self.discount_percent) / Decimal("100")
            ).quantize(Decimal("0.01"))
        return Decimal("0.00")

    @property
    def effective_price(self):
        """Net payable unit price after catalog markdown or a live product offer."""
        from apps.promotions.services import unit_price_for

        return unit_price_for(self)

    @property
    def sale_percent(self):
        if not self.selling_price:
            return Decimal("0")
        saved = self.selling_price - self.effective_price
        if saved <= 0:
            return Decimal("0")
        return (saved * Decimal("100") / self.selling_price).quantize(Decimal("1"))

    @property
    def offer_badge(self):
        from apps.promotions.services import product_offer_badge

        return product_offer_badge(self)

    @property
    def has_discount(self):
        return self.effective_price < self.selling_price

    @property
    def average_cost(self):
        return self.purchase_price

    @property
    def unit_profit(self):
        return (self.effective_price - self.purchase_price).quantize(Decimal("0.01"))

    @property
    def stock_value(self):
        qty = max(self.stock_quantity or 0, 0)
        return (self.purchase_price * qty).quantize(Decimal("0.01"))

    def _usable_image(self, fieldfile):
        from config.storage import resolve_public_media

        name = getattr(fieldfile, "name", "") if fieldfile else ""
        return fieldfile if resolve_public_media(name) else None

    @property
    def cover_image(self):
        """Main photo, falling back to the first gallery file that actually exists."""
        main = self._usable_image(self.image)
        if main:
            return main
        gallery = list(self.images.all())
        for row in gallery:
            found = self._usable_image(row.image)
            if found:
                return found
        return None

    def get_available_stock(self):
        """On-hand minus reserved across warehouses."""
        if self.variant_parent_id:
            return self._own_available_stock()
        variants = self._related_variants()
        if variants:
            own_stock = self._own_available_stock() if self.size else 0
            return own_stock + sum(variant._own_available_stock() for variant in variants if variant.is_active)
        return self._own_available_stock()

    def _own_available_stock(self):
        if (
            hasattr(self, "_prefetched_objects_cache")
            and "inventories" in self._prefetched_objects_cache
        ):
            return sum(inv.available_stock for inv in self.inventories.all())
        from apps.inventory.services import available_stock

        return available_stock(self)

    def _related_variants(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("variants")
        if prefetched is not None:
            return list(prefetched)
        return list(self.variants.all())

    @property
    def has_variants(self):
        if self.variant_parent_id:
            return False
        return bool(self._related_variants())

    @property
    def variant_sizes(self):
        if self.variant_parent_id:
            return []
        variants = [variant for variant in self._related_variants() if variant.is_active]
        sizes = ([self.size] if self.size else []) + [
            variant.size for variant in variants if variant.size
        ]
        return list(dict.fromkeys(sizes))

    @property
    def in_stock(self):
        return self.get_available_stock() > 0

    @property
    def is_low_stock(self):
        return self.get_available_stock() <= self.min_stock_level

    @property
    def subcategory(self):
        if self.category_id and self.category.parent_id:
            return self.category
        return None

    @property
    def root_category(self):
        if not self.category_id:
            return None
        return self.category.parent or self.category


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=150, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Image for {self.product.sku}"

    @property
    def file_exists(self):
        from config.storage import resolve_public_media

        return bool(resolve_public_media(getattr(self.image, "name", "")))
