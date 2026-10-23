from django.conf import settings
from django.db import models


class Warehouse(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Inventory(models.Model):
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="inventories"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="inventories"
    )
    current_stock = models.IntegerField(default=0)
    reserved_stock = models.IntegerField(default=0)
    incoming_stock = models.IntegerField(default=0)
    sold_quantity = models.IntegerField(default=0)
    returned_quantity = models.IntegerField(default=0)
    damaged_quantity = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "inventories"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "warehouse"], name="uniq_product_warehouse"
            )
        ]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["warehouse"]),
        ]

    def __str__(self):
        return f"{self.product.sku} @ {self.warehouse.code}"

    @property
    def available_stock(self):
        return self.current_stock - self.reserved_stock


class StockTransaction(models.Model):
    class Type(models.TextChoices):
        GRN = "grn", "GRN"
        SALE = "sale", "Sale"
        CUSTOMER_RETURN = "customer_return", "Customer Return"
        ADJUSTMENT = "adjustment", "Stock Adjustment"
        DAMAGE = "damage", "Damage"
        CORRECTION = "correction", "Manual Correction"
        RESERVE = "reserve", "Reserve"
        RELEASE = "release", "Release Reserve"
        INCOMING = "incoming", "Incoming"

    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="stock_transactions"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="stock_transactions"
    )
    quantity = models.IntegerField(help_text="Signed quantity. Positive increases stock.")
    transaction_type = models.CharField(max_length=30, choices=Type.choices)
    reference = models.CharField(max_length=80, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction_type", "created_at"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return f"{self.transaction_type} {self.quantity} {self.product.sku}"


class InventoryCostLayer(models.Model):
    """FIFO cost layer. Historical GRN purchase rate is frozen here."""

    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="cost_layers"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="cost_layers"
    )
    grn = models.ForeignKey(
        "purchases.GRN",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_layers",
    )
    grn_item = models.ForeignKey(
        "purchases.GRNItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_layers",
    )
    purchase_rate = models.DecimalField(max_digits=12, decimal_places=2)
    received_qty = models.PositiveIntegerField()
    remaining_qty = models.PositiveIntegerField()
    batch_number = models.CharField(max_length=50, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["received_at", "id"]
        indexes = [
            models.Index(fields=["product", "warehouse", "received_at"]),
            models.Index(fields=["remaining_qty"]),
        ]

    def __str__(self):
        return f"{self.product_id} @ {self.warehouse_id} {self.remaining_qty} x {self.purchase_rate}"

    @property
    def remaining_value(self):
        return self.purchase_rate * self.remaining_qty


class CostLayerConsumption(models.Model):
    class Kind(models.TextChoices):
        SALE = "sale", "Sale"
        RESTORE = "restore", "Restore"
        WRITE_OFF = "write_off", "Write-off"

    layer = models.ForeignKey(
        InventoryCostLayer, on_delete=models.PROTECT, related_name="consumptions"
    )
    order_item = models.ForeignKey(
        "orders.OrderItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_consumptions",
    )
    return_item = models.ForeignKey(
        "returns.ReturnItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cost_consumptions",
    )
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    reference = models.CharField(max_length=80, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.kind} {self.quantity} @ {self.unit_cost}"

