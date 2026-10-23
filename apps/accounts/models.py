from django.contrib.auth.models import AbstractUser
from django.db import models


class StaffModule(models.TextChoices):
    DASHBOARD = "dashboard", "Dashboard"
    USERS = "users", "Users & Permissions"
    PRODUCTS = "products", "Products"
    CATEGORIES = "categories", "Categories"
    BRANDS = "brands", "Brands"
    VENDORS = "vendors", "Vendors"
    GRN = "grn", "GRN"
    WAREHOUSES = "warehouses", "Warehouses"
    INVENTORY = "inventory", "Inventory"
    CUSTOMERS = "customers", "Customers"
    ORDERS = "orders", "Orders"
    RETURNS = "returns", "Returns"
    REVIEWS = "reviews", "Reviews"
    PROMOTIONS = "promotions", "Promotions"
    PAYMENTS = "payments", "Payments"
    PAYMENT_METHODS = "payment_methods", "Payment Methods"
    ACCOUNTING = "accounting", "Accounting"
    EXPENSES = "expenses", "Expenses"
    VENDOR_PAYMENTS = "vendor_payments", "Vendor Payments"


class User(AbstractUser):
    class UserType(models.TextChoices):
        STAFF = "staff", "Staff"
        CUSTOMER = "customer", "Customer"

    class AccessMode(models.TextChoices):
        FULL = "full", "Full access"
        VIEWER = "viewer", "Viewer (read only)"

    user_type = models.CharField(
        max_length=20, choices=UserType.choices, default=UserType.CUSTOMER
    )
    phone = models.CharField(max_length=20, blank=True)
    profile_image = models.ImageField(upload_to="profiles/", blank=True, null=True)
    allowed_modules = models.JSONField(default=list, blank=True)
    access_mode = models.CharField(
        max_length=20,
        choices=AccessMode.choices,
        default=AccessMode.FULL,
        help_text="Viewers can open assigned modules but cannot add, edit, or delete records.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["user_type"]),
            models.Index(fields=["email"]),
        ]

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.user_type = self.UserType.STAFF
            self.is_staff = True
        elif self.user_type == self.UserType.STAFF:
            self.is_staff = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_staff_user(self):
        return self.is_superuser or self.user_type == self.UserType.STAFF
