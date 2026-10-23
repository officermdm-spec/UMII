from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from config.media import protected_media
from config.views import healthz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("django-admin/", admin.site.urls),
    path("staff/login/", RedirectView.as_view(pattern_name="accounts:staff_login", permanent=False)),
    path("staff/accounts/", include("apps.accounts.urls")),
    path("staff/", include("apps.dashboard.urls")),
    path("staff/categories/", include("apps.categories.urls")),
    path("staff/vendors/", include("apps.vendors.urls")),
    path("staff/products/", include("apps.products.urls")),
    path("staff/inventory/", include("apps.inventory.urls")),
    path("staff/grn/", include("apps.purchases.urls")),
    path("staff/orders/", include("apps.orders.urls_staff")),
    path("staff/payments/", include("apps.payments.urls")),
    path("staff/returns/", include("apps.returns.urls_staff")),
    path("staff/reviews/", include("apps.reviews.urls_staff")),
    path("staff/promotions/", include("apps.promotions.urls")),
    path("staff/accounting/", include("apps.accounting.urls")),
    path("staff/vendor-payments/", include("apps.vendor_payments.urls")),
    path("staff/customers/", include("apps.customers.urls_staff")),
    path("account/", include("apps.customers.urls")),
    path("cart/", include("apps.orders.urls_cart")),
    path("checkout/", include("apps.orders.urls_checkout")),
    path("orders/", include("apps.orders.urls_customer")),
    path("returns/", include("apps.returns.urls_customer")),
    path("reviews/", include("apps.reviews.urls_customer")),
    path("", include("apps.products.urls_store")),
]

urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        protected_media,
    ),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
