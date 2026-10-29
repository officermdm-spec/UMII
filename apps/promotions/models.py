from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def _lifecycle(is_active, start_date, end_date, usage_limit=None, used_count=0):
    now = timezone.now()
    if not is_active:
        return "disabled"
    if start_date > now:
        return "scheduled"
    if end_date < now:
        return "expired"
    if usage_limit is not None and used_count >= usage_limit:
        return "exhausted"
    return "active"


class ProductOffer(models.Model):
    class OfferType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage discount"
        FIXED = "fixed", "Fixed amount discount"
        BUY_X_GET_Y = "buy_x_get_y", "Buy X Get Y"

    name = models.CharField("Offer name", max_length=150)
    offer_type = models.CharField(
        max_length=20, choices=OfferType.choices, default=OfferType.PERCENTAGE
    )
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percent or rupee amount. Ignored for Buy X Get Y.",
    )
    buy_qty = models.PositiveIntegerField(default=0)
    get_qty = models.PositiveIntegerField(default=0)
    products = models.ManyToManyField(
        "products.Product", blank=True, related_name="product_offers"
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField("Active", default=True)
    show_on_website = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["is_active", "start_date", "end_date"]),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be after the start date."})
        if self.offer_type == self.OfferType.BUY_X_GET_Y:
            if not self.buy_qty or not self.get_qty:
                raise ValidationError("Buy X Get Y needs both buy quantity and get quantity.")
        elif self.value is None or self.value <= 0:
            raise ValidationError({"value": "Enter a discount greater than zero."})

    @property
    def lifecycle(self):
        return _lifecycle(self.is_active, self.start_date, self.end_date)

    @property
    def discount_label(self):
        if self.offer_type == self.OfferType.BUY_X_GET_Y:
            return f"Buy {self.buy_qty} Get {self.get_qty}"
        if self.offer_type == self.OfferType.PERCENTAGE:
            return f"{self.value.quantize(Decimal('1'))}% off"
        return f"Rs. {self.value} off"
