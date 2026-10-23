from django.contrib import admin, messages

from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import PaymentError, sync_payment_status


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "method", "amount", "status", "transaction_id", "created_at")
    list_filter = ("status", "method")
    list_editable = ("status",)
    search_fields = ("order__order_number", "transaction_id")
    readonly_fields = ("order", "method", "amount", "proof_image", "created_at", "paid_at", "gateway_response")

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            return

        original = Payment.objects.get(pk=obj.pk)
        new_status = form.cleaned_data.get("status", obj.status)
        transaction_id = form.cleaned_data.get("transaction_id", obj.transaction_id)

        # Keep non-status fields; sync service owns status + order.payment_status.
        obj.status = original.status
        super().save_model(request, obj, form, change)
        obj.refresh_from_db()

        if new_status != original.status or transaction_id != original.transaction_id:
            try:
                sync_payment_status(obj, new_status, transaction_id=transaction_id or "")
            except PaymentError as exc:
                messages.error(request, f"Payment status not updated: {exc}")
