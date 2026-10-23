from django.urls import path

from apps.orders.views import ApplyCouponView, CheckoutView, RemoveCouponView

app_name = "orders_checkout"

urlpatterns = [
    path("", CheckoutView.as_view(), name="checkout"),
    path("coupon/apply/", ApplyCouponView.as_view(), name="apply_coupon"),
    path("coupon/remove/", RemoveCouponView.as_view(), name="remove_coupon"),
]
