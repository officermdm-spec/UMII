from django.urls import path

from apps.vendor_payments import views

app_name = "vendor_payments"

urlpatterns = [
    path("", views.VendorPaymentListView.as_view(), name="list"),
    path("add/", views.VendorPaymentCreateView.as_view(), name="create"),
    path("<int:pk>/", views.VendorPaymentDetailView.as_view(), name="detail"),
    path("<int:pk>/void/", views.VendorPaymentVoidView.as_view(), name="void"),
]
