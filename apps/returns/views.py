from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, FormView, ListView, View

from apps.accounts.mixins import CustomerRequiredMixin, ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.orders.models import Order, OrderItem
from apps.returns.forms import ReturnProcessForm, ReturnRequestForm
from apps.returns.models import ReturnImage, ReturnItem, ReturnRequest
from apps.returns.services import ReturnError, update_return_status


class CustomerReturnListView(CustomerRequiredMixin, ListView):
    template_name = "customers/return_list.html"
    context_object_name = "returns"

    def get_queryset(self):
        return ReturnRequest.objects.filter(customer=self.request.user)


class CustomerReturnDetailView(CustomerRequiredMixin, DetailView):
    template_name = "customers/return_detail.html"
    context_object_name = "return_request"

    def get_queryset(self):
        return ReturnRequest.objects.filter(customer=self.request.user).prefetch_related("items", "images")


class CustomerReturnCreateView(CustomerRequiredMixin, FormView):
    template_name = "customers/return_form.html"
    form_class = ReturnRequestForm

    def dispatch(self, request, *args, **kwargs):
        self.order = get_object_or_404(Order, pk=kwargs["order_id"], customer=request.user)
        if self.order.status not in {Order.Status.DELIVERED, Order.Status.RECEIVED}:
            messages.error(request, "Returns can only be requested for delivered orders.")
            return redirect("orders_customer:detail", pk=self.order.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = self.order
        return context

    def form_valid(self, form):
        selected = self.request.POST.getlist("item")
        if not selected:
            form.add_error(None, "Select at least one item to return.")
            return self.form_invalid(form)
        with transaction.atomic():
            ret = ReturnRequest.objects.create(
                order=self.order,
                customer=self.request.user,
                reason=form.cleaned_data["reason"],
                description=form.cleaned_data.get("description", ""),
            )
            for item_id in selected:
                order_item = get_object_or_404(OrderItem, pk=item_id, order=self.order)
                qty = int(self.request.POST.get(f"qty_{item_id}", 1) or 1)
                qty = max(1, min(qty, order_item.quantity))
                ReturnItem.objects.create(
                    return_request=ret,
                    order_item=order_item,
                    product=order_item.product,
                    quantity=qty,
                )
            for image in self.request.FILES.getlist("images"):
                ReturnImage.objects.create(return_request=ret, image=image)
        messages.success(self.request, f"Return {ret.return_number} submitted.")
        return redirect("returns_customer:detail", pk=ret.pk)


class StaffReturnListView(ModulePermissionMixin, ListView):
    module = MODULES.RETURNS
    model = ReturnRequest
    template_name = "staff/returns/list.html"
    context_object_name = "returns"
    paginate_by = 20

    def get_queryset(self):
        qs = ReturnRequest.objects.select_related("customer", "order")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs


class StaffReturnDetailView(ModulePermissionMixin, DetailView):
    module = MODULES.RETURNS
    model = ReturnRequest
    template_name = "staff/returns/detail.html"
    context_object_name = "return_request"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = ReturnProcessForm(instance=self.object)
        context["conditions"] = ReturnItem.Condition.choices
        return context


class StaffReturnDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.RETURNS
    model = ReturnRequest
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("returns_staff:list")
    delete_blocked_message = "Only new return requests can be deleted."
    delete_success_message = "Return request deleted."

    def delete_is_allowed(self):
        return self.object.status == ReturnRequest.Status.REQUESTED


class StaffReturnProcessView(ModulePermissionMixin, View):
    module = MODULES.RETURNS
    def post(self, request, pk):
        ret = get_object_or_404(ReturnRequest, pk=pk)
        form = ReturnProcessForm(request.POST, instance=ret)
        if form.is_valid():
            for item in ret.items.all():
                condition = request.POST.get(f"condition_{item.pk}")
                if condition:
                    item.condition = condition
                    item.save(update_fields=["condition"])
            try:
                update_return_status(
                    ret,
                    form.cleaned_data["status"],
                    user=request.user,
                    staff_notes=form.cleaned_data.get("staff_notes", ""),
                )
                messages.success(request, "Return updated.")
            except ReturnError as exc:
                messages.error(request, str(exc))
        return redirect("returns_staff:detail", pk=pk)
