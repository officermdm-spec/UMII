from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from config.utils import next_document_number


class GRN(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        CANCELLED = "cancelled", "Cancelled"

    grn_number = models.CharField(max_length=30, unique=True, blank=True)
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.PROTECT, related_name="grns"
    )
    grn_date = models.DateField(default=timezone.localdate)
    purchase_reference = models.CharField(max_length=80, blank=True)
    invoice_number = models.CharField(max_length=80, blank=True)
    warehouse = models.ForeignKey(
        "inventory.Warehouse", on_delete=models.PROTECT, related_name="grns"
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="received_grns",
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_grns",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "GRN"
        verbose_name_plural = "GRNs"
        indexes = [
            models.Index(fields=["grn_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["vendor", "grn_date"]),
        ]

    def save(self, *args, **kwargs):
        if not self.grn_number:
            self.grn_number = next_document_number(GRN, "grn_number", "GRN")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.grn_number

    @property
    def is_locked(self):
        return self.status in {self.Status.APPROVED, self.Status.CANCELLED}

    @property
    def can_edit(self):
        return not self.is_locked

    @property
    def grand_total(self):
        return sum((item.line_total for item in self.items.all()), Decimal("0.00"))


class GRNItem(models.Model):
    grn = models.ForeignKey(GRN, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="grn_items"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    purchase_rate = models.DecimalField(max_digits=12, decimal_places=2)
    batch_number = models.CharField(max_length=50, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    average_cost_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Product weighted-average cost after this line was approved.",
    )

    class Meta:
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.line_total = (self.purchase_rate or Decimal("0.00")) * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.grn.grn_number} - {self.product.sku}"

    @property
    def item_code(self):
        return self.product.sku


class ProductPurchaseHistory(models.Model):
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="purchase_history"
    )
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="purchase_history"
    )
    grn = models.ForeignKey(GRN, on_delete=models.CASCADE, related_name="purchase_history")
    quantity = models.PositiveIntegerField()
    purchase_rate = models.DecimalField(max_digits=12, decimal_places=2)
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-purchased_at"]
        verbose_name_plural = "product purchase histories"
