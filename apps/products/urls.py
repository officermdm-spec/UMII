from django.urls import path

from apps.products import views

app_name = "products"

urlpatterns = [
    path("", views.ProductListView.as_view(), name="list"),
    path("lookup/", views.ProductBarcodeLookupView.as_view(), name="lookup"),
    path("add/", views.ProductCreateView.as_view(), name="create"),
    path("brands/", views.BrandListView.as_view(), name="brand_list"),
    path("brands/add/", views.BrandCreateView.as_view(), name="brand_create"),
    path("brands/<int:pk>/edit/", views.BrandUpdateView.as_view(), name="brand_update"),
    path("brands/<int:pk>/delete/", views.BrandDeleteView.as_view(), name="brand_delete"),
    path("<int:pk>/", views.ProductDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ProductUpdateView.as_view(), name="update"),
    path("<int:pk>/barcode/", views.ProductBarcodePrintView.as_view(), name="barcode_print"),
    path("<int:pk>/barcode.png", views.ProductBarcodeImageView.as_view(), name="barcode_png"),
    path("<int:pk>/barcode/download/", views.ProductBarcodeDownloadView.as_view(), name="barcode_download"),
    path("<int:pk>/barcode/regenerate/", views.ProductBarcodeRegenerateView.as_view(), name="barcode_regenerate"),
    path("<int:pk>/delete/", views.ProductDeleteView.as_view(), name="delete"),
]
