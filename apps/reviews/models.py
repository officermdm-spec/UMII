from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Review(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, related_name="reviews"
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField()
    is_approved = models.BooleanField(null=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "product", "order"], name="uniq_review_customer_product_order"
            )
        ]

    def __str__(self):
        return f"{self.product} ({self.rating}/5)"

    @property
    def status_label(self):
        if self.is_approved is True:
            return "Approved"
        if self.is_approved is False:
            return "Rejected"
        return "Pending"


class Feedback(models.Model):
    class Topic(models.TextChoices):
        PRODUCT = "product", "Product"
        ORDER = "order", "Order"
        DELIVERY = "delivery", "Delivery"
        PAYMENT = "payment", "Payment"
        WEBSITE = "website", "Website"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_REVIEW = "in_review", "In review"
        REPLIED = "replied", "Replied"
        CLOSED = "closed", "Closed"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedback"
    )
    topic = models.CharField(max_length=20, choices=Topic.choices, default=Topic.OTHER)
    rating = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    subject = models.CharField(max_length=150)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    staff_reply = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_replies",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "feedback"

    def __str__(self):
        return self.subject

    def mark_replied(self, user, reply, status=None):
        self.staff_reply = reply
        self.replied_by = user
        self.replied_at = timezone.now()
        self.status = status or self.Status.REPLIED
        self.save(
            update_fields=["staff_reply", "replied_by", "replied_at", "status"]
        )
