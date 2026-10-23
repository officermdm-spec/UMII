from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.promotions.forms import ProductOfferForm, PromotionForm
from apps.promotions.models import ProductOffer, Promotion


class CouponListView(ModulePermissionMixin, ListView):
    module = MODULES.PROMOTIONS
    model = Promotion
    template_name = "staff/promotions/list.html"
    context_object_name = "promotions"
    paginate_by = 20

    def get_queryset(self):
        return Promotion.objects.prefetch_related("products")


class PromotionListView(CouponListView):
    """Kept so existing promotions:list URL and imports keep working."""


class PromotionCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.PROMOTIONS
    form_class = PromotionForm
    template_name = "staff/promotions/form.html"
    success_url = reverse_lazy("promotions:list")

    def form_valid(self, form):
        messages.success(self.request, "Coupon saved.")
        return super().form_valid(form)


class PromotionUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.PROMOTIONS
    model = Promotion
    form_class = PromotionForm
    template_name = "staff/promotions/form.html"
    success_url = reverse_lazy("promotions:list")

    def form_valid(self, form):
        messages.success(self.request, "Coupon updated.")
        return super().form_valid(form)


class PromotionDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.PROMOTIONS
    model = Promotion
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("promotions:list")
    delete_success_message = "Coupon deleted."


class ProductOfferListView(ModulePermissionMixin, ListView):
    module = MODULES.PROMOTIONS
    model = ProductOffer
    template_name = "staff/promotions/offer_list.html"
    context_object_name = "offers"
    paginate_by = 20

    def get_queryset(self):
        return ProductOffer.objects.prefetch_related("products")


class ProductOfferCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.PROMOTIONS
    form_class = ProductOfferForm
    template_name = "staff/promotions/offer_form.html"
    success_url = reverse_lazy("promotions:offer_list")

    def form_valid(self, form):
        messages.success(self.request, "Product offer saved.")
        return super().form_valid(form)


class ProductOfferUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.PROMOTIONS
    model = ProductOffer
    form_class = ProductOfferForm
    template_name = "staff/promotions/offer_form.html"
    success_url = reverse_lazy("promotions:offer_list")

    def form_valid(self, form):
        messages.success(self.request, "Product offer updated.")
        return super().form_valid(form)


class ProductOfferDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.PROMOTIONS
    model = ProductOffer
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("promotions:offer_list")
    delete_success_message = "Product offer deleted."
