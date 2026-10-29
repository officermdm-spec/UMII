from django.urls import path

from apps.orders.views import CheckoutView

app_name = "orders_checkout"

urlpatterns = [
    path("", CheckoutView.as_view(), name="checkout"),
]
