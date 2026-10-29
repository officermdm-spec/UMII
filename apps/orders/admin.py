from django.contrib import admin, messages

from apps.orders.models import CartItem, Order, OrderItem, OrderStatusHistory
from apps.orders.services import OrderError, change_order_status
from apps.payments.services import PaymentError, set_order_payment_status


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "sku",
        "product_name",
        "product_size",
        "product_color",
        "quantity",
        "unit_price",
        "discount",
        "tax",
        "total",
    )
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("status", "note", "changed_by", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer",
        "status",
        "payment_status",
        "grand_total",
        "created_at",
    )
    list_filter = ("status", "payment_status", "payment_method_code", "created_at")
    search_fields = ("order_number", "customer__username", "customer__email", "billing_phone")
    list_editable = ("status", "payment_status")
    readonly_fields = (
        "order_number",
        "customer",
        "payment_method_code",
        "subtotal",
        "discount",
        "shipping_charge",
        "tax",
        "grand_total",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "order_number",
                    "customer",
                    "status",
                    "payment_status",
                    "payment_method_code",
                    "notes",
                )
            },
        ),
        (
            "Totals",
            {
                "fields": (
                    "subtotal",
                    "discount",
                    "shipping_charge",
                    "tax",
                    "grand_total",
                )
            },
        ),
        (
            "Billing",
            {
                "fields": (
                    "billing_full_name",
                    "billing_phone",
                    "billing_address",
                    "billing_city",
                    "billing_area",
                    "billing_postal_code",
                )
            },
        ),
        (
            "Shipping",
            {
                "fields": (
                    "shipping_full_name",
                    "shipping_phone",
                    "shipping_address",
                    "shipping_city",
                    "shipping_area",
                    "shipping_postal_code",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            super().save_model(request, obj, form, change)
            return

        original = Order.objects.get(pk=obj.pk)
        new_status = form.cleaned_data.get("status", obj.status)
        new_payment_status = form.cleaned_data.get("payment_status", obj.payment_status)

        # Persist non-status fields first without clobbering status transitions.
        obj.status = original.status
        obj.payment_status = original.payment_status
        super().save_model(request, obj, form, change)

        if new_status != original.status:
            try:
                change_order_status(
                    obj,
                    new_status,
                    user=request.user,
                    note="Updated via Django admin",
                )
            except OrderError as exc:
                self.message_user(
                    request, f"Order status not updated: {exc}", level=messages.ERROR
                )

        if new_payment_status != original.payment_status:
            try:
                obj.refresh_from_db()
                set_order_payment_status(obj, new_payment_status)
            except PaymentError as exc:
                self.message_user(
                    request, f"Payment status not updated: {exc}", level=messages.ERROR
                )


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "quantity")


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "changed_by", "created_at")
    list_filter = ("status",)
    search_fields = ("order__order_number",)
