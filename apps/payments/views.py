from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.payments.forms import PaymentMethodForm, PaymentStatusForm
from apps.payments.models import Payment, PaymentMethod
from apps.payments.services import PaymentError, mark_failed, mark_paid, sync_payment_status


class PaymentMethodListView(ModulePermissionMixin, ListView):
    module = MODULES.PAYMENT_METHODS
    model = PaymentMethod
    template_name = "staff/payments/methods.html"
    context_object_name = "methods"


class PaymentMethodCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.PAYMENT_METHODS
    form_class = PaymentMethodForm
    template_name = "staff/payments/method_form.html"
    success_url = reverse_lazy("payments:methods")

    def form_valid(self, form):
        messages.success(self.request, "Payment method created.")
        return super().form_valid(form)


class PaymentMethodUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.PAYMENT_METHODS
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = "staff/payments/method_form.html"
    success_url = reverse_lazy("payments:methods")


class PaymentMethodDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.PAYMENT_METHODS
    model = PaymentMethod
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("payments:methods")
    delete_protected_message = "This payment method has payments and cannot be deleted. Deactivate it instead."


class PaymentListView(ModulePermissionMixin, ListView):
    module = MODULES.PAYMENTS
    model = Payment
    template_name = "staff/payments/list.html"
    context_object_name = "payments"
    paginate_by = 20

    def get_queryset(self):
        return Payment.objects.select_related("order", "method")


class PaymentDetailView(ModulePermissionMixin, DetailView):
    module = MODULES.PAYMENTS
    model = Payment
    template_name = "staff/payments/detail.html"
    context_object_name = "payment"

    def get_queryset(self):
        return Payment.objects.select_related("order", "method", "order__customer")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = PaymentStatusForm(instance=self.object)
        return context


def _payment_redirect(request, payment):
    next_url = request.POST.get("next") or ""
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("payments:detail", pk=payment.pk)


class PaymentStatusUpdateView(ModulePermissionMixin, View):
    module = MODULES.PAYMENTS

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        form = PaymentStatusForm(request.POST, instance=payment)
        if not form.is_valid():
            messages.error(request, "Invalid payment status.")
            return _payment_redirect(request, payment)
        try:
            sync_payment_status(
                payment,
                form.cleaned_data["status"],
                transaction_id=form.cleaned_data.get("transaction_id", ""),
            )
            messages.success(request, "Payment status updated.")
        except PaymentError as exc:
            messages.error(request, str(exc))
        return _payment_redirect(request, payment)


class PaymentMarkPaidView(ModulePermissionMixin, View):
    module = MODULES.PAYMENTS

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        mark_paid(payment, transaction_id=request.POST.get("transaction_id", ""))
        messages.success(request, "Payment marked as paid.")
        return _payment_redirect(request, payment)


class PaymentMarkFailedView(ModulePermissionMixin, View):
    module = MODULES.PAYMENTS

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        mark_failed(payment)
        messages.info(request, "Payment marked as failed.")
        return _payment_redirect(request, payment)
