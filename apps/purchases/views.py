from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from django.core.exceptions import PermissionDenied

from apps.accounts.mixins import ModulePermissionMixin
from apps.accounts.permissions import MODULES, is_admin_user
from apps.products.models import Product
from apps.purchases.forms import GRNForm, GRNItemFormSet
from apps.purchases.models import GRN
from apps.purchases.services import GRNError, approve_grn, delete_grn, unapprove_grn


class GRNFormMixin:
    def get_formset(self, instance=None):
        kwargs = {}
        if instance is not None:
            kwargs["instance"] = instance
        if self.request.method == "POST":
            return GRNItemFormSet(self.request.POST, **kwargs)
        return GRNItemFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None)
        if "formset" not in context:
            context["formset"] = self.get_formset(instance)
        context["today"] = timezone.localdate()
        context["product_rates"] = {
            str(product.pk): str(product.purchase_price)
            for product in Product.objects.filter(is_active=True).only("id", "purchase_price")
        }
        return context


class GRNListView(ModulePermissionMixin, ListView):
    module = MODULES.GRN
    model = GRN
    template_name = "staff/grn/list.html"
    context_object_name = "grns"
    paginate_by = 20

    def get_queryset(self):
        qs = GRN.objects.select_related("vendor", "warehouse")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(grn_number__icontains=q)
                | Q(vendor__name__icontains=q)
                | Q(invoice_number__icontains=q)
            )
        return qs


class GRNCreateView(GRNFormMixin, ModulePermissionMixin, CreateView):
    module = MODULES.GRN
    form_class = GRNForm
    template_name = "staff/grn/form.html"

    def form_valid(self, form):
        formset = self.get_formset()
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.received_by = self.request.user
            self.object.grn_date = timezone.localdate()
            self.object.status = GRN.Status.PENDING
            self.object.save()
            formset.instance = self.object
            formset.save()
        messages.success(self.request, f"{self.object.grn_number} saved as pending.")
        return redirect("purchases:list")


class GRNUpdateView(GRNFormMixin, ModulePermissionMixin, UpdateView):
    module = MODULES.GRN
    model = GRN
    form_class = GRNForm
    template_name = "staff/grn/form.html"

    def get_queryset(self):
        return GRN.objects.exclude(status__in=[GRN.Status.APPROVED, GRN.Status.CANCELLED])

    def form_valid(self, form):
        formset = self.get_formset(self.object)
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        with transaction.atomic():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
        messages.success(self.request, f"{self.object.grn_number} updated.")
        return redirect("purchases:list")


class GRNDetailView(ModulePermissionMixin, DetailView):
    module = MODULES.GRN
    model = GRN
    template_name = "staff/grn/detail.html"
    context_object_name = "grn"

    def get_queryset(self):
        return GRN.objects.select_related("vendor", "warehouse", "received_by", "approved_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_unapprove"] = (
            self.object.status == GRN.Status.APPROVED and is_admin_user(self.request.user)
        )
        return context


class GRNDeleteView(ModulePermissionMixin, DeleteView):
    module = MODULES.GRN
    model = GRN
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("purchases:list")

    def get_queryset(self):
        return GRN.objects.exclude(status__in=[GRN.Status.APPROVED, GRN.Status.CANCELLED])

    def form_valid(self, form):
        try:
            number = delete_grn(self.object)
        except GRNError as exc:
            messages.error(self.request, str(exc))
            return redirect("purchases:detail", pk=self.object.pk)
        messages.success(self.request, f"{number} deleted.")
        return redirect(self.success_url)


class GRNApproveView(ModulePermissionMixin, View):
    module = MODULES.GRN

    def post(self, request, pk):
        grn = get_object_or_404(GRN, pk=pk)
        try:
            approve_grn(grn, request.user)
            messages.success(request, f"{grn.grn_number} approved. Stock increased.")
        except GRNError as exc:
            messages.error(request, str(exc))
        return redirect("purchases:detail", pk=pk)


class GRNUnapproveView(ModulePermissionMixin, View):
    module = MODULES.GRN

    def post(self, request, pk):
        if not is_admin_user(request.user):
            raise PermissionDenied("Only an admin can unapprove a GRN.")
        grn = get_object_or_404(GRN, pk=pk)
        try:
            unapprove_grn(grn, request.user)
            messages.success(request, f"{grn.grn_number} unapproved. Inventory was reverted.")
        except PermissionDenied:
            raise
        except GRNError as exc:
            messages.error(request, str(exc))
        return redirect("purchases:detail", pk=pk)
