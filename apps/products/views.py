from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES, has_module_permission
from apps.categories.models import Category
from apps.products.barcode import (
    BarcodeLookupError,
    get_product_by_barcode,
    render_barcode_png,
)
from apps.products.forms import BrandForm, ProductForm, ProductVariantFormSet
from apps.products.models import Brand, Product, ProductImage
from apps.promotions.services import live_promotions


class ProductListView(ModulePermissionMixin, ListView):
    module = MODULES.PRODUCTS
    model = Product
    template_name = "staff/products/list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        qs = Product.objects.select_related("category", "vendor", "brand")
        q = self.request.GET.get("q")
        category = self.request.GET.get("category")
        vendor = self.request.GET.get("vendor")
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(sku__icontains=q) | Q(barcode__icontains=q)
            )
        if category:
            qs = qs.filter(Q(category_id=category) | Q(category__parent_id=category))
        if vendor:
            qs = qs.filter(vendor_id=vendor)
        return qs


class ProductCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.PRODUCTS
    form_class = ProductForm
    template_name = "staff/products/form.html"
    success_url = reverse_lazy("products:list")

    def get_variant_formset(self):
        if not hasattr(self, "_variant_formset"):
            data = self.request.POST if self.request.method == "POST" else None
            instance = self.object or Product()
            self._variant_formset = ProductVariantFormSet(data, instance=instance)
        return self._variant_formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["variant_formset"] = self.get_variant_formset()
        return context

    @transaction.atomic
    def form_valid(self, form):
        self._variant_formset = ProductVariantFormSet(
            self.request.POST, instance=form.instance
        )
        if not self._variant_formset.is_valid():
            return self.form_invalid(form)
        self.object = form.save()
        _save_product_images(self.request, self.object)
        self._variant_formset.instance = self.object
        self._variant_formset.save()
        _sync_product_variants(self.object)
        messages.success(self.request, "Product created.")
        return redirect(self.get_success_url())


class ProductUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.PRODUCTS
    model = Product
    form_class = ProductForm
    template_name = "staff/products/form.html"
    success_url = reverse_lazy("products:list")

    def get_variant_formset(self):
        if self.object.variant_parent_id:
            return None
        if not hasattr(self, "_variant_formset"):
            data = self.request.POST if self.request.method == "POST" else None
            self._variant_formset = ProductVariantFormSet(data, instance=self.object)
        return self._variant_formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["gallery"] = self.object.images.all()
        context["variant_formset"] = self.get_variant_formset()
        return context

    @transaction.atomic
    def form_valid(self, form):
        variant_formset = self.get_variant_formset()
        if variant_formset and not variant_formset.is_valid():
            return self.form_invalid(form)
        self.object = form.save()
        _save_product_images(self.request, self.object)
        if variant_formset:
            variant_formset.instance = self.object
            variant_formset.save()
            _sync_product_variants(self.object)
        messages.success(self.request, "Product updated.")
        return redirect(self.get_success_url())


class ProductDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.PRODUCTS
    model = Product
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("products:list")
    delete_protected_message = "This product has orders, stock history, or GRNs and cannot be deleted."


class BrandListView(ModulePermissionMixin, ListView):
    module = MODULES.BRANDS
    model = Brand
    template_name = "staff/products/brands.html"
    context_object_name = "brands"
    paginate_by = 20

    def get_queryset(self):
        qs = Brand.objects.all().order_by("name")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
        return qs


class BrandCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.BRANDS
    form_class = BrandForm
    template_name = "staff/products/brand_form.html"
    success_url = reverse_lazy("products:brand_list")

    def form_valid(self, form):
        messages.success(self.request, "Brand created.")
        return super().form_valid(form)


class BrandUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.BRANDS
    model = Brand
    form_class = BrandForm
    template_name = "staff/products/brand_form.html"
    success_url = reverse_lazy("products:brand_list")

    def form_valid(self, form):
        messages.success(self.request, "Brand updated.")
        return super().form_valid(form)


class BrandDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.BRANDS
    model = Brand
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("products:brand_list")
    delete_protected_message = "This brand is used by products and cannot be deleted."


class ProductDetailView(ModulePermissionMixin, DetailView):
    module = MODULES.PRODUCTS
    model = Product
    template_name = "staff/products/detail.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["variants"] = (
            self.object.variants.select_related("variant_parent")
            .prefetch_related("inventories")
            .all()
            if not self.object.variant_parent_id
            else []
        )
        return context


class ProductBarcodePrintView(ModulePermissionMixin, DetailView):
    module = MODULES.PRODUCTS
    model = Product
    template_name = "staff/products/barcode_print.html"
    context_object_name = "product"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            copies = int(self.request.GET.get("copies") or 1)
        except (TypeError, ValueError):
            copies = 1
        context["copies"] = max(1, min(copies, 100))
        context["copy_range"] = range(context["copies"])
        return context


class ProductBarcodeImageView(ModulePermissionMixin, View):
    module = MODULES.PRODUCTS

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        png = render_barcode_png(product.barcode)
        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = f'inline; filename="{product.barcode}.png"'
        response["Cache-Control"] = "no-store"
        return response


class ProductBarcodeDownloadView(ModulePermissionMixin, View):
    module = MODULES.PRODUCTS

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        png = render_barcode_png(product.barcode)
        response = HttpResponse(png, content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="{product.sku}-{product.barcode}.png"'
        return response


class ProductBarcodeRegenerateView(ModulePermissionMixin, View):
    module = MODULES.PRODUCTS

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        if request.POST.get("confirm") != "1":
            messages.error(request, "Confirm barcode regeneration before continuing.")
            return redirect("products:detail", pk=product.pk)
        from apps.products.barcode import allocate_unique_barcode
        from apps.accounting.services import record_audit

        old = product.barcode
        product.barcode = allocate_unique_barcode()
        product.save(update_fields=["barcode", "updated_at"])
        record_audit(
            request.user,
            "barcode_regenerated",
            reference_type="product",
            reference_id=product.pk,
            notes=f"{old} → {product.barcode}",
        )
        messages.success(request, f"Barcode regenerated to {product.barcode}.")
        return redirect("products:detail", pk=product.pk)


class ProductBarcodeLookupView(View):
    allowed_modules = (MODULES.PRODUCTS, MODULES.GRN, MODULES.INVENTORY, MODULES.ORDERS)

    def dispatch(self, request, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        from django.urls import reverse as url_reverse

        if not request.user.is_authenticated:
            return redirect(f"{url_reverse('accounts:staff_login')}?next={request.get_full_path()}")
        if not any(has_module_permission(request.user, module) for module in self.allowed_modules):
            raise PermissionDenied("You do not have permission to look up products.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        try:
            product = get_product_by_barcode(request.GET.get("barcode", ""))
        except BarcodeLookupError as exc:
            return JsonResponse({"ok": False, "error": str(exc), "code": exc.code}, status=404)
        return JsonResponse(
            {
                "ok": True,
                "id": product.pk,
                "name": product.name,
                "sku": product.sku,
                "barcode": product.barcode,
                "purchase_price": str(product.purchase_price),
                "selling_price": str(product.selling_price),
            }
        )


def _save_product_images(request, product):
    """Handle main image, gallery uploads, deletes, and set-as-main."""
    changed = False

    if request.POST.get("clear_main_image") and product.image:
        product.image.delete(save=False)
        product.image = None
        changed = True

    main_file = request.FILES.get("main_image")
    if main_file:
        product.image = main_file
        changed = True

    delete_ids = request.POST.getlist("delete_images")
    if delete_ids:
        ProductImage.objects.filter(product=product, pk__in=delete_ids).delete()

    set_main_id = request.POST.get("set_main_image")
    if set_main_id:
        gallery_image = ProductImage.objects.filter(product=product, pk=set_main_id).first()
        if gallery_image:
            product.image = gallery_image.image
            changed = True

    gallery_files = request.FILES.getlist("gallery")
    created = []
    if gallery_files:
        start = product.images.count()
        for index, image in enumerate(gallery_files):
            created.append(
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    alt_text=product.name,
                    sort_order=start + index,
                )
            )
        if not product.image and created:
            product.image = created[0].image
            changed = True

    if changed:
        product.save(update_fields=["image", "updated_at"])
        product.refresh_from_db()
        if not product.image and created:
            Product.objects.filter(pk=product.pk).update(image=created[0].image)
            product.refresh_from_db()


def _sync_product_variants(product):
    Product.objects.filter(variant_parent=product).update(
        name=product.name,
        category=product.category,
        vendor=product.vendor,
        brand=product.brand,
        description=product.description,
        image=product.image.name if product.image else "",
        selling_price=product.selling_price,
        purchase_price=product.purchase_price,
        unit=product.unit,
        tax_percent=product.tax_percent,
        discount_percent=product.discount_percent,
        min_stock_level=product.min_stock_level,
    )


class StoreHomeView(ListView):
    template_name = "store/home.html"
    context_object_name = "featured_products"

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True, variant_parent__isnull=True)
            .select_related("category")
            .prefetch_related(
                "inventories",
                "images",
                "product_offers",
                "variants__inventories",
            )[:8]
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(is_active=True, parent__isnull=True)
        context["deals"] = (
            Product.objects.filter(
                is_active=True, variant_parent__isnull=True, discount_percent__gt=0
            )
            .select_related("category")
            .prefetch_related(
                "inventories",
                "images",
                "product_offers",
                "variants__inventories",
            )[:4]
        )
        context["live_promotions"] = live_promotions()[:8]
        return context


class StoreProductListView(ListView):
    template_name = "store/product_list.html"
    context_object_name = "products"
    paginate_by = 12

    def get_queryset(self):
        qs = (
            Product.objects.filter(is_active=True, variant_parent__isnull=True)
            .select_related("category", "brand")
            .prefetch_related(
                "inventories",
                "images",
                "product_offers",
                "variants__inventories",
                "variants__product_offers",
            )
        )
        q = self.request.GET.get("q")
        category = self.request.GET.get("category")
        min_price = self.request.GET.get("min_price")
        max_price = self.request.GET.get("max_price")
        sort = self.request.GET.get("sort", "newest")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(description__icontains=q)
                | Q(variants__is_active=True, variants__sku__icontains=q)
                | Q(variants__is_active=True, variants__size__icontains=q)
            ).distinct()
        if category:
            qs = qs.filter(Q(category__slug=category) | Q(category__parent__slug=category))
        if min_price:
            qs = qs.filter(selling_price__gte=min_price)
        if max_price:
            qs = qs.filter(selling_price__lte=max_price)
        sort_map = {
            "price_asc": "selling_price",
            "price_desc": "-selling_price",
            "name": "name",
            "newest": "-created_at",
        }
        return qs.order_by(sort_map.get(sort, "-created_at"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(is_active=True)
        context["current_category"] = self.request.GET.get("category", "")
        context["q"] = self.request.GET.get("q", "")
        context["sort"] = self.request.GET.get("sort", "newest")
        return context


class StoreCategoryView(StoreProductListView):
    def get_queryset(self):
        self.category = get_object_or_404(Category, slug=self.kwargs["slug"], is_active=True)
        qs = super().get_queryset()
        return qs.filter(Q(category=self.category) | Q(category__parent=self.category))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_category"] = self.category.slug
        context["category_obj"] = self.category
        return context


class StoreProductDetailView(DetailView):
    template_name = "store/product_detail.html"
    model = Product
    context_object_name = "product"
    slug_field = "slug"

    def get_queryset(self):
        return (
            Product.objects.filter(is_active=True)
            .filter(Q(variant_parent__isnull=True) | Q(variant_parent__is_active=True))
            .select_related("category", "vendor", "brand")
            .prefetch_related(
                "inventories",
                "images",
                "product_offers",
                "variants__inventories",
                "variants__product_offers",
            )
        )

    def get_object(self, queryset=None):
        product = super().get_object(queryset)
        if product.variant_parent_id:
            return product.variant_parent
        return product

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        child_variants = [
            variant
            for variant in product._related_variants()
            if variant.is_active
        ]
        context["variant_options"] = (
            ([product] if product.size else []) + child_variants
            if product.has_variants
            else []
        )
        context["gallery"] = [img for img in product.images.all() if img.file_exists]
        context["reviews"] = product.reviews.filter(is_approved=True).select_related("customer")
        context["avg_rating"] = context["reviews"].aggregate(avg=Avg("rating"))["avg"]
        context["related"] = (
            Product.objects.filter(
                is_active=True,
                variant_parent__isnull=True,
                category=product.category,
            )
            .exclude(pk=product.pk)
            .prefetch_related("inventories", "images", "product_offers")[:4]
        )
        request_url = self.request.build_absolute_uri(product.get_absolute_url())
        context["whatsapp_message"] = (
            f"Hello, I need information about this product.\n"
            f"Product: {product.name}\n"
            f"Item Code: {product.sku}\n"
            f"URL: {request_url}"
        )
        return context
