from django.urls import path

from apps.inventory import views

app_name = "inventory"

urlpatterns = [
    path("", views.InventoryListView.as_view(), name="list"),
    path("low-stock/", views.LowStockListView.as_view(), name="low_stock"),
    path("transactions/", views.StockTransactionListView.as_view(), name="transactions"),
    path("adjust/", views.StockAdjustmentView.as_view(), name="adjust"),
    path("min-stock/", views.MinStockLevelView.as_view(), name="min_stock"),
    path("warehouses/", views.WarehouseListView.as_view(), name="warehouse_list"),
    path("warehouses/add/", views.WarehouseCreateView.as_view(), name="warehouse_create"),
    path("warehouses/<int:pk>/edit/", views.WarehouseUpdateView.as_view(), name="warehouse_update"),
    path("warehouses/<int:pk>/delete/", views.WarehouseDeleteView.as_view(), name="warehouse_delete"),
]
