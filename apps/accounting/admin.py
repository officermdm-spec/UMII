from django.contrib import admin

from apps.accounting.models import Account, AuditLog, Expense, JournalEntry, OtherIncome, VendorPayment


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "account_type", "is_active")
    search_fields = ("code", "name")


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("number", "entry_at", "reference_type", "description", "status")
    readonly_fields = ("number", "entry_at", "reference_type", "reference_id", "description", "status")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("category", "amount", "date", "status")


@admin.register(OtherIncome)
class OtherIncomeAdmin(admin.ModelAdmin):
    list_display = ("title", "amount", "date", "status")


@admin.register(VendorPayment)
class VendorPaymentAdmin(admin.ModelAdmin):
    list_display = ("vendor", "amount", "date", "status")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "amount")
    readonly_fields = ("user", "action", "reference_type", "reference_id", "amount", "notes", "created_at")

    def has_delete_permission(self, request, obj=None):
        return False
