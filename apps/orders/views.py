from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, FormView, ListView, TemplateView, View

from apps.accounts.mixins import CustomerRequiredMixin, ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.inventory.services import available_stock
from apps.orders.cart import add_to_cart, cart_summary, remove_from_cart, set_quantity
from apps.orders.forms import CheckoutForm, OrderPaymentStatusForm, OrderStatusForm
from apps.orders.models import Order
from apps.orders.services import (
    STATUS_FLOW,
    OrderError,
    build_order_tracker,
    change_order_status,
    issue_invoice,
    place_order,
)
from apps.payments.models import PaymentMethod
from apps.payments.services import PaymentError, set_order_payment_status
from apps.products.models import Product
from config.utils import safe_internal_url


class CartView(TemplateView):
    template_name = "store/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["summary"] = cart_summary(self.request)
        return context


class AddToCartView(View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, is_active=True)
        catalog_product = product.variant_parent or product
        if not catalog_product.is_active:
            raise Http404
        variants = list(catalog_product.variants.filter(is_active=True))
        if catalog_product.has_variants:
            selected_id = request.POST.get("variant_id")
            options = [
                option
                for option in variants + ([catalog_product] if catalog_product.size else [])
                if available_stock(option) > 0
            ]
            selected = next(
                (option for option in options if str(option.pk) == str(selected_id)),
                None,
            )
            if selected is None:
                messages.error(request, "Please select an available size.")
                return redirect(catalog_product.get_absolute_url())
            product = selected
        try:
            qty = int(request.POST.get("quantity", 1) or 1)
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, min(qty, 999))
        available = available_stock(product)
        if qty > available:
            messages.error(request, f"Only {available} unit(s) available.")
            return redirect(product.get_absolute_url())
        add_to_cart(request, product, qty)
        size_label = f" ({product.size})" if product.size else ""
        messages.success(request, f"{product.name}{size_label} added to cart.")
        return redirect(safe_internal_url(request.POST.get("next"), "orders_cart:cart"))


class UpdateCartView(View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        try:
            qty = int(request.POST.get("quantity", 0) or 0)
        except (TypeError, ValueError):
            qty = 0
        available = available_stock(product)
        if qty > available:
            messages.error(request, f"Only {available} unit(s) available for {product.name}.")
            return redirect("orders_cart:cart")
        set_quantity(request, product, qty)
        messages.success(request, "Cart updated.")
        return redirect("orders_cart:cart")


class RemoveCartView(View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        remove_from_cart(request, product)
        messages.info(request, "Item removed.")
        return redirect("orders_cart:cart")


class CheckoutView(CustomerRequiredMixin, FormView):
    template_name = "store/checkout.html"
    form_class = CheckoutForm
    success_url = reverse_lazy("orders_customer:list")

    def dispatch(self, request, *args, **kwargs):
        summary = cart_summary(request)
        if request.user.is_authenticated and not summary["items"]:
            messages.info(request, "Your cart is empty.")
            return redirect("orders_cart:cart")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = cart_summary(self.request)
        context["summary"] = summary
        context["payment_method_codes"] = {
            str(m.pk): m.code
            for m in PaymentMethod.objects.filter(is_active=True)
        }
        return context

    def form_valid(self, form):
        billing = form.cleaned_data["billing_address"]
        shipping = billing if form.cleaned_data.get("same_as_billing") else form.cleaned_data["shipping_address"]
        try:
            order = place_order(
                request=self.request,
                billing_address=billing,
                shipping_address=shipping,
                payment_method=form.cleaned_data["payment_method"],
                notes=form.cleaned_data.get("notes", ""),
                payment_proof=form.cleaned_data.get("payment_proof"),
            )
        except OrderError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f"Order {order.order_number} placed successfully.")
        return redirect("orders_customer:detail", pk=order.pk)


class CustomerOrderListView(CustomerRequiredMixin, ListView):
    template_name = "customers/order_list.html"
    context_object_name = "orders"
    paginate_by = 10

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user)


class CustomerOrderDetailView(CustomerRequiredMixin, DetailView):
    template_name = "customers/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).prefetch_related(
            "items", "status_history", "payments"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_cancel"] = self.object.status == Order.Status.PENDING
        context["needs_cancel_contact"] = self.object.status in {
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.IN_PROGRESS,
            Order.Status.ON_WAY,
        }
        context["can_mark_received"] = self.object.status == Order.Status.DELIVERED
        context["tracker"] = build_order_tracker(self.object)
        context["cancel_whatsapp_message"] = (
            f"Hello, I want to cancel order {self.object.order_number}."
        )
        context["can_print_invoice"] = bool(self.object.invoice_number)
        return context


class CustomerCancelOrderView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, customer=request.user)
        if order.status != Order.Status.PENDING:
            messages.error(
                request,
                "Confirmed orders cannot be cancelled here. Email us or contact us on WhatsApp.",
            )
            return redirect("orders_customer:detail", pk=pk)
        try:
            change_order_status(order, Order.Status.CANCELLED, user=request.user, note="Cancelled by customer")
            messages.info(request, "Order cancelled.")
        except OrderError as exc:
            messages.error(request, str(exc))
        return redirect("orders_customer:detail", pk=pk)


class CustomerReceiveOrderView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, customer=request.user)
        try:
            change_order_status(
                order,
                Order.Status.RECEIVED,
                user=request.user,
                note="Customer confirmed receipt",
            )
            messages.success(request, "Thanks — order marked as received.")
        except OrderError as exc:
            messages.error(request, str(exc))
        return redirect("orders_customer:detail", pk=pk)


class StaffOrderListView(ModulePermissionMixin, ListView):
    module = MODULES.ORDERS
    template_name = "staff/orders/list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related("customer")
        status = self.request.GET.get("status")
        payment_status = self.request.GET.get("payment_status")
        q = self.request.GET.get("q")
        if status:
            qs = qs.filter(status=status)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if q:
            qs = qs.filter(order_number__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = [
            choice
            for choice in Order.Status.choices
            if choice[0] not in {Order.Status.IN_PROGRESS, Order.Status.ON_WAY}
        ]
        context["payment_statuses"] = Order.PaymentStatus.choices
        return context


class StaffOrderDetailView(ModulePermissionMixin, DetailView):
    module = MODULES.ORDERS
    model = Order
    template_name = "staff/orders/detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("customer").prefetch_related(
            "items", "status_history", "payments", "payments__method"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        allowed = STATUS_FLOW.get(self.object.status, set())
        if self.request.user.is_superuser:
            allowed = {
                value for value, _ in Order.Status.choices if value != self.object.status
            }
        allowed = {s for s in allowed if s not in {Order.Status.IN_PROGRESS, Order.Status.ON_WAY}}
        choices = [(s, dict(Order.Status.choices)[s]) for s in allowed]
        context["status_form"] = OrderStatusForm(choices=choices)
        context["payment_status_form"] = OrderPaymentStatusForm(
            current=self.object.payment_status
        )
        context["can_update_status"] = bool(choices)
        context["tracker"] = build_order_tracker(self.object)
        context["can_print_invoice"] = self.object.status in {
            Order.Status.PROCESSING,
            Order.Status.DELIVERED,
            Order.Status.RECEIVED,
            Order.Status.IN_PROGRESS,
            Order.Status.ON_WAY,
        } or bool(self.object.invoice_number)
        return context


class OrderInvoiceMixin:
    template_name = "print/thermal_invoice.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["invoice_number"] = self.object.invoice_number or "—"
        return context


class StaffOrderInvoiceView(OrderInvoiceMixin, ModulePermissionMixin, DetailView):
    module = MODULES.ORDERS
    model = Order

    def get_queryset(self):
        return Order.objects.select_related("customer").prefetch_related("items", "payments")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status in {
            Order.Status.PROCESSING,
            Order.Status.DELIVERED,
            Order.Status.RECEIVED,
            Order.Status.IN_PROGRESS,
            Order.Status.ON_WAY,
        }:
            issue_invoice(self.object)
            self.object.refresh_from_db()
        elif not self.object.invoice_number:
            raise Http404()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class CustomerOrderInvoiceView(OrderInvoiceMixin, CustomerRequiredMixin, DetailView):
    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).prefetch_related("items", "payments")

    def get_object(self, queryset=None):
        order = super().get_object(queryset)
        if not order.invoice_number:
            raise Http404()
        return order


class StaffOrderStatusView(ModulePermissionMixin, View):
    module = MODULES.ORDERS

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        allowed = STATUS_FLOW.get(order.status, set())
        if request.user.is_superuser:
            allowed = {value for value, _ in Order.Status.choices if value != order.status}
        allowed = {s for s in allowed if s not in {Order.Status.IN_PROGRESS, Order.Status.ON_WAY}}
        choices = [(s, dict(Order.Status.choices)[s]) for s in allowed]
        form = OrderStatusForm(request.POST, choices=choices)
        if not form.is_valid():
            messages.error(request, "Invalid order status.")
            return redirect("orders_staff:detail", pk=pk)
        try:
            change_order_status(
                order,
                form.cleaned_data["status"],
                user=request.user,
                note=form.cleaned_data.get("note", ""),
            )
            messages.success(request, "Order status updated.")
        except OrderError as exc:
            messages.error(request, str(exc))
        return redirect("orders_staff:detail", pk=pk)


class StaffOrderPaymentStatusView(ModulePermissionMixin, View):
    module = MODULES.ORDERS

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderPaymentStatusForm(request.POST, current=order.payment_status)
        if not form.is_valid():
            messages.error(request, "Invalid payment status.")
            return redirect("orders_staff:detail", pk=pk)
        try:
            set_order_payment_status(
                order,
                form.cleaned_data["payment_status"],
                transaction_id=form.cleaned_data.get("transaction_id", ""),
            )
            messages.success(request, "Payment status updated.")
        except PaymentError as exc:
            messages.error(request, str(exc))
        return redirect("orders_staff:detail", pk=pk)


class StaffOrderDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.ORDERS
    model = Order
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("orders_staff:list")
    delete_blocked_message = "Only pending orders can be cancelled from this action."
    delete_success_message = "Order cancelled."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["confirm_title"] = "Cancel this pending order?"
        context["confirm_label"] = "Cancel order"
        context["confirm_message"] = "Stock reservations will be released. Confirmed orders cannot be deleted."
        context["cancel_url"] = reverse_lazy("orders_staff:list")
        return context

    def delete_is_allowed(self):
        return self.object.status == Order.Status.PENDING

    def form_valid(self, form):
        if not self.delete_is_allowed():
            messages.error(self.request, self.delete_blocked_message)
            return redirect("orders_staff:detail", pk=self.object.pk)
        try:
            change_order_status(self.object, Order.Status.CANCELLED, user=self.request.user, note="Cancelled from staff list.")
        except OrderError as exc:
            messages.error(self.request, str(exc))
            return redirect("orders_staff:detail", pk=self.object.pk)
        messages.success(self.request, self.delete_success_message)
        return redirect(self.success_url)
