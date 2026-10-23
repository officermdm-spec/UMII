from django.contrib import admin

from apps.inventory.models import Inventory, InventoryCostLayer, StockTransaction, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "current_stock", "reserved_stock")


@admin.register(InventoryCostLayer)
class InventoryCostLayerAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "purchase_rate", "received_qty", "remaining_qty", "received_at")
    list_filter = ("warehouse",)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("product", "transaction_type", "quantity", "reference", "created_at")
    list_filter = ("transaction_type",)
