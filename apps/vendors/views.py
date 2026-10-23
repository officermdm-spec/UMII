from django.contrib import messages
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.purchases.models import GRN, ProductPurchaseHistory
from apps.vendors.forms import VendorForm
from apps.vendors.models import Vendor


class VendorListView(ModulePermissionMixin, ListView):
    module = MODULES.VENDORS
    model = Vendor
    template_name = "staff/vendors/list.html"
    context_object_name = "vendors"
    paginate_by = 20

    def get_queryset(self):
        qs = Vendor.objects.all()
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(company_name__icontains=q) | Q(phone__icontains=q)
            )
        return qs


class VendorCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.VENDORS
    form_class = VendorForm
    template_name = "staff/vendors/form.html"
    success_url = reverse_lazy("vendors:list")

    def form_valid(self, form):
        messages.success(self.request, "Vendor created.")
        return super().form_valid(form)


class VendorUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.VENDORS
    model = Vendor
    form_class = VendorForm
    template_name = "staff/vendors/form.html"
    success_url = reverse_lazy("vendors:list")

    def form_valid(self, form):
        messages.success(self.request, "Vendor updated.")
        return super().form_valid(form)


class VendorDetailView(ModulePermissionMixin, DetailView):
    module = MODULES.VENDORS
    model = Vendor
    template_name = "staff/vendors/detail.html"
    context_object_name = "vendor"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["grns"] = GRN.objects.filter(vendor=self.object).select_related("warehouse")[:50]
        context["purchase_history"] = ProductPurchaseHistory.objects.filter(
            vendor=self.object
        ).select_related("product", "grn")[:50]
        return context


class VendorDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.VENDORS
    model = Vendor
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("vendors:list")
    delete_protected_message = "This vendor has GRNs or payments and cannot be deleted."
