from uuid import uuid4

from django.contrib import messages
from django.db.models import F, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView, View

from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.inventory.forms import MinStockLevelForm, StockAdjustmentForm, WarehouseForm
from apps.inventory.models import Inventory, StockTransaction, Warehouse
from apps.inventory.services import StockError, inventory_health, record_stock_transaction, visible_inventory_q
from apps.products.models import Product


class InventoryListView(ModulePermissionMixin, ListView):
    module = MODULES.INVENTORY
    template_name = "staff/inventory/list.html"
    context_object_name = "inventories"
    paginate_by = 20

    def get_queryset(self):
        qs = Inventory.objects.select_related("product", "warehouse", "product__category").filter(
            visible_inventory_q()
        )
        q = self.request.GET.get("q")
        low = self.request.GET.get("low")
        warehouse = self.request.GET.get("warehouse")
        status = self.request.GET.get("status")
        if q:
            qs = qs.filter(
                Q(product__name__icontains=q)
                | Q(product__sku__icontains=q)
                | Q(product__barcode__icontains=q)
            )
        if warehouse:
            qs = qs.filter(warehouse_id=warehouse)
        qs = qs.annotate(available=F("current_stock") - F("reserved_stock"))
        if low or status == "low":
            qs = qs.filter(available__lte=F("product__min_stock_level"))
        if status == "out":
            qs = qs.filter(available__lte=0)
        return qs.order_by("product__name", "warehouse__code")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["warehouses"] = Warehouse.objects.filter(is_active=True)
        rows = []
        for inv in context["inventories"]:
            rows.append(
                {
                    "inv": inv,
                    "health": inventory_health(inv),
                    "min_form": MinStockLevelForm(
                        initial={
                            "product": inv.product_id,
                            "min_stock_level": inv.product.min_stock_level,
                        }
                    ),
                }
            )
        context["inventory_rows"] = rows
        context["status_filter"] = self.request.GET.get("status", "")
        context["warehouse_filter"] = self.request.GET.get("warehouse", "")
        return context


class StockTransactionListView(ModulePermissionMixin, ListView):
    module = MODULES.INVENTORY
    model = StockTransaction
    template_name = "staff/inventory/transactions.html"
    context_object_name = "transactions"
    paginate_by = 30

    def get_queryset(self):
        qs = StockTransaction.objects.select_related("product", "warehouse", "user")
        q = self.request.GET.get("q")
        txn_type = self.request.GET.get("type")
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(reference__icontains=q))
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["txn_types"] = StockTransaction.Type.choices
        context["type_filter"] = self.request.GET.get("type", "")
        return context


class StockAdjustmentView(ModulePermissionMixin, FormView):
    module = MODULES.INVENTORY
    form_class = StockAdjustmentForm
    template_name = "staff/inventory/adjust.html"
    success_url = reverse_lazy("inventory:list")

    def form_valid(self, form):
        product = form.cleaned_data["product"]
        try:
            record_stock_transaction(
                product=product,
                warehouse=form.cleaned_data["warehouse"],
                quantity=form.cleaned_data["quantity"],
                transaction_type=form.cleaned_data["transaction_type"],
                reference=f"ADJ-{uuid4().hex[:12].upper()}",
                user=self.request.user,
                notes=form.cleaned_data.get("notes", ""),
            )
        except StockError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        min_level = form.cleaned_data.get("min_stock_level")
        if min_level is not None:
            Product.objects.filter(pk=product.pk).update(min_stock_level=min_level)
            product.min_stock_level = min_level
        product.refresh_from_db()
        messages.success(
            self.request,
            f"Stock updated for {product.sku}. On-hand is now {product.stock_quantity} "
            f"(min {product.min_stock_level}).",
        )
        return super().form_valid(form)


class MinStockLevelView(ModulePermissionMixin, View):
    module = MODULES.INVENTORY

    def post(self, request):
        form = MinStockLevelForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Could not update minimum stock level.")
            return redirect("inventory:list")
        product = form.cleaned_data["product"]
        product.min_stock_level = form.cleaned_data["min_stock_level"]
        product.save(update_fields=["min_stock_level", "updated_at"])
        messages.success(
            request,
            f"Minimum stock for {product.sku} is now {product.min_stock_level}.",
        )
        return redirect("inventory:list")


class LowStockListView(InventoryListView):
    def get_queryset(self):
        return (
            Inventory.objects.select_related("product", "warehouse", "product__category")
            .filter(visible_inventory_q())
            .annotate(available=F("current_stock") - F("reserved_stock"))
            .filter(available__lte=F("product__min_stock_level"))
            .order_by("available", "product__name")
        )


class WarehouseListView(ModulePermissionMixin, ListView):
    module = MODULES.WAREHOUSES
    model = Warehouse
    template_name = "staff/inventory/warehouses.html"
    context_object_name = "warehouses"
    paginate_by = 20

    def get_queryset(self):
        qs = Warehouse.objects.all()
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(address__icontains=q))
        return qs


class WarehouseCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.WAREHOUSES
    form_class = WarehouseForm
    template_name = "staff/inventory/warehouse_form.html"
    success_url = reverse_lazy("inventory:warehouse_list")

    def form_valid(self, form):
        messages.success(self.request, "Warehouse created.")
        return super().form_valid(form)


class WarehouseUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.WAREHOUSES
    model = Warehouse
    form_class = WarehouseForm
    template_name = "staff/inventory/warehouse_form.html"
    success_url = reverse_lazy("inventory:warehouse_list")

    def form_valid(self, form):
        messages.success(self.request, "Warehouse updated.")
        return super().form_valid(form)


class WarehouseDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.WAREHOUSES
    model = Warehouse
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("inventory:warehouse_list")
    delete_protected_message = "This warehouse has stock history and cannot be deleted. Deactivate it instead."
