from django.conf import settings
from django.db import models

from config.utils import next_document_number


class ReturnRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PICKUP_SCHEDULED = "pickup_scheduled", "Pickup Scheduled"
        RECEIVED = "received", "Received"
        INSPECTED = "inspected", "Inspected"
        REFUND_PENDING = "refund_pending", "Refund Pending"
        REFUNDED = "refunded", "Refunded"
        COMPLETED = "completed", "Completed"

    return_number = models.CharField(max_length=30, unique=True, blank=True)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, related_name="return_requests"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="return_requests"
    )
    reason = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.REQUESTED
    )
    staff_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["return_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["customer"]),
        ]

    def save(self, *args, **kwargs):
        if not self.return_number:
            self.return_number = next_document_number(
                ReturnRequest, "return_number", "RET"
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.return_number


class ReturnItem(models.Model):
    class Condition(models.TextChoices):
        RESELLABLE = "resellable", "Resellable"
        DAMAGED = "damaged", "Damaged"
        MISSING = "missing", "Missing"

    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name="items"
    )
    order_item = models.ForeignKey(
        "orders.OrderItem", on_delete=models.PROTECT, related_name="return_items"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, related_name="return_items"
    )
    quantity = models.PositiveIntegerField()
    condition = models.CharField(
        max_length=20, choices=Condition.choices, default=Condition.RESELLABLE
    )

    def __str__(self):
        return f"{self.return_request.return_number} x {self.quantity}"


class ReturnImage(models.Model):
    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="returns/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
