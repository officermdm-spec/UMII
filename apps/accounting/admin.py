from django.contrib import admin

from apps.accounting.models import Account, AuditLog, Expense, VendorPayment


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "account_type", "is_active")
    search_fields = ("code", "name")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("category", "amount", "date", "status")


@admin.register(VendorPayment)
class VendorPaymentAdmin(admin.ModelAdmin):
    list_display = ("vendor", "amount", "date", "status")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "user", "amount")
    readonly_fields = ("user", "action", "reference_type", "reference_id", "amount", "notes", "created_at")

    def has_delete_permission(self, request, obj=None):
        return False
