from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from config.utils import next_document_number


class CartItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="cart_items"
    )
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="uniq_cart_user_product")
        ]

    def __str__(self):
        return f"{self.user} x {self.quantity} {self.product.sku}"

    @property
    def line_total(self):
        return self.product.effective_price * self.quantity


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        IN_PROGRESS = "in_progress", "In Progress"
        ON_WAY = "on_way", "On Way"
        DELIVERED = "delivered", "Delivered"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"
        RETURN_REQUESTED = "return_requested", "Return Requested"
        RETURNED = "returned", "Returned"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"
        COD_PENDING = "cod_pending", "COD Pending"

    order_number = models.CharField(max_length=30, unique=True, blank=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    billing_full_name = models.CharField(max_length=150)
    billing_phone = models.CharField(max_length=20)
    billing_address = models.TextField()
    billing_city = models.CharField(max_length=100)
    billing_area = models.CharField(max_length=100, blank=True)
    billing_postal_code = models.CharField(max_length=20, blank=True)
    shipping_full_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=20)
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_area = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    payment_method_code = models.CharField(max_length=40)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_charge = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    catalog_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    offer_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    cogs_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    fulfillment_warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fulfilled_orders",
    )
    notes = models.TextField(blank=True)
    invoice_number = models.CharField(max_length=30, unique=True, blank=True, null=True)
    invoiced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order_number"], name="orders_orde_order_n_f3ada5_idx"),
            models.Index(fields=["customer", "created_at"], name="orders_orde_custome_242823_idx"),
            models.Index(fields=["status"], name="orders_orde_status_c6dd84_idx"),
            models.Index(fields=["payment_status"], name="orders_orde_payment_bc131d_idx"),
            models.Index(fields=["invoice_number"], name="orders_orde_invoice_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = next_document_number(Order, "order_number", "ORD")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    sku = models.CharField(max_length=50)
    product_name = models.CharField(max_length=200)
    product_size = models.CharField(max_length=50, blank=True)
    product_color = models.CharField(max_length=50, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)
    catalog_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    offer_discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    cogs_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Average cost snapshot at sale time.",
    )

    def __str__(self):
        return f"{self.order.order_number} - {self.product_name}"

class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=30, choices=Order.Status.choices)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "order status histories"

    def __str__(self):
        return f"{self.order.order_number} -> {self.status}"
