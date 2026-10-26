from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounting.coa import AccountType
from config.utils import next_document_number


class Account(models.Model):
    class Type(models.TextChoices):
        ASSET = AccountType.ASSET, "Asset"
        LIABILITY = AccountType.LIABILITY, "Liability"
        EQUITY = AccountType.EQUITY, "Equity"
        REVENUE = AccountType.REVENUE, "Revenue"
        CONTRA_REVENUE = AccountType.CONTRA_REVENUE, "Contra revenue"
        EXPENSE = AccountType.EXPENSE, "Expense"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=20, choices=Type.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class JournalEntry(models.Model):
    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    number = models.CharField(max_length=30, unique=True, blank=True)
    entry_at = models.DateTimeField(default=timezone.now)
    reference_type = models.CharField(max_length=40)
    reference_id = models.CharField(max_length=40)
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entries",
    )
    reversed_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversals_of",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entry_at", "-id"]
        indexes = [
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["entry_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_document_number(JournalEntry, "number", "JE")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number

    @property
    def total_debit(self):
        return sum((line.debit for line in self.lines.all()), Decimal("0.00"))

    @property
    def total_credit(self):
        return sum((line.credit for line in self.lines.all()), Decimal("0.00"))


class JournalLine(models.Model):
    journal = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    credit = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))]
    )
    memo = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.journal.number} {self.account.code}"


class AccountingPosting(models.Model):
    event_key = models.CharField(max_length=120, unique=True)
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="postings")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.event_key


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounting_audit_logs",
    )
    action = models.CharField(max_length=80)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.CharField(max_length=40, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Expense(models.Model):
    class Category(models.TextChoices):
        RENT = "rent", "Rent"
        SALARIES = "salaries", "Salaries"
        ELECTRICITY = "electricity", "Electricity"
        INTERNET = "internet", "Internet"
        MARKETING = "marketing", "Marketing"
        DELIVERY = "delivery", "Delivery"
        PACKAGING = "packaging", "Packaging"
        MAINTENANCE = "maintenance", "Maintenance"
        OFFICE = "office", "Office"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"
    category = models.CharField(max_length=30, choices=Category.choices)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    date = models.DateField(default=timezone.localdate)
    payment_account = models.CharField(max_length=20, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    receipt = models.ImageField(upload_to="accounting/expenses/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.get_category_display()} - {self.date}"


class OtherIncome(models.Model):
    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    title = models.CharField(max_length=160)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    date = models.DateField(default=timezone.localdate)
    payment_account = models.CharField(max_length=20, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    attachment = models.FileField(upload_to="accounting/income/", blank=True, null=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="other_incomes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.title


class VendorPayment(models.Model):
    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        VOID = "void", "Void"

    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.PROTECT, related_name="vendor_payments"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    date = models.DateField(default=timezone.localdate)
    payment_account = models.CharField(max_length=20, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
