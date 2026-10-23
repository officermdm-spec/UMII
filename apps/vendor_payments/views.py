from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from apps.accounting.coa import ZERO, money
from apps.accounting.forms import VendorPaymentForm
from apps.accounting.models import VendorPayment
from apps.accounts.mixins import ModulePermissionMixin
from apps.accounts.permissions import MODULES, has_module_permission
from apps.purchases.models import GRN, GRNItem
from apps.vendor_payments.services import VendorPaymentError, record_vendor_payment, void_vendor_payment
from apps.vendors.models import Vendor


class VendorPaymentsMixin(ModulePermissionMixin):
    module = MODULES.VENDOR_PAYMENTS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["can_accounting"] = has_module_permission(user, MODULES.ACCOUNTING)
        context["can_expenses"] = has_module_permission(user, MODULES.EXPENSES)
        context["can_vendor_payments"] = has_module_permission(user, MODULES.VENDOR_PAYMENTS)
        return context


def _payable_rows():
    purchase_map = {
        row["grn__vendor_id"]: money(row["total"] or ZERO)
        for row in GRNItem.objects.filter(grn__status=GRN.Status.APPROVED)
        .values("grn__vendor_id")
        .annotate(total=Sum("line_total"))
    }
    paid_map = {
        row["vendor_id"]: money(row["total"] or ZERO)
        for row in VendorPayment.objects.filter(status=VendorPayment.Status.POSTED)
        .values("vendor_id")
        .annotate(total=Sum("amount"))
    }
    rows = []
    for vendor in Vendor.objects.filter(is_active=True).order_by("name"):
        purchases = purchase_map.get(vendor.pk, ZERO)
        paid = paid_map.get(vendor.pk, ZERO)
        rows.append(
            {
                "vendor": vendor,
                "purchases": purchases,
                "paid": paid,
                "outstanding": money(purchases - paid),
            }
        )
    return rows


class VendorPaymentListView(VendorPaymentsMixin, ListView):
    model = VendorPayment
    template_name = "staff/vendor_payments/list.html"
    context_object_name = "payments"
    paginate_by = 20

    def get_queryset(self):
        qs = VendorPayment.objects.select_related("vendor", "created_by")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(vendor__name__icontains=q) | Q(reference__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = _payable_rows()
        context["rows"] = rows
        context["total"] = sum((row["outstanding"] for row in rows), ZERO)
        return context


class VendorPaymentCreateView(VendorPaymentsMixin, CreateView):
    form_class = VendorPaymentForm
    template_name = "staff/vendor_payments/form.html"
    success_url = reverse_lazy("vendor_payments:list")

    def form_valid(self, form):
        payment = form.save(commit=False)
        payment.created_by = self.request.user
        record_vendor_payment(payment, self.request.user)
        messages.success(self.request, "Vendor payment posted.")
        return redirect(self.success_url)


class VendorPaymentDetailView(VendorPaymentsMixin, DetailView):
    model = VendorPayment
    template_name = "staff/vendor_payments/detail.html"
    context_object_name = "payment"

    def get_queryset(self):
        return VendorPayment.objects.select_related("vendor", "created_by")


class VendorPaymentVoidView(ModulePermissionMixin, View):
    module = MODULES.VENDOR_PAYMENTS

    def get(self, request, pk):
        payment = get_object_or_404(VendorPayment.objects.select_related("vendor"), pk=pk)
        return render(
            request,
            "staff/confirm_delete.html",
            {
                "object": payment,
                "object_label": f"Vendor payment #{payment.pk} to {payment.vendor}",
                "cancel_url": reverse("vendor_payments:detail", kwargs={"pk": payment.pk}),
                "confirm_label": "Void payment",
            },
        )

    def post(self, request, pk):
        payment = get_object_or_404(VendorPayment, pk=pk)
        try:
            void_vendor_payment(payment, request.user)
        except VendorPaymentError as exc:
            messages.error(request, str(exc))
            return redirect("vendor_payments:detail", pk=payment.pk)
        messages.success(request, "Vendor payment voided and ledger reversed.")
        return redirect("vendor_payments:list")
