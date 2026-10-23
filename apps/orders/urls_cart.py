from django.urls import path

from apps.orders import views

app_name = "orders_cart"

urlpatterns = [
    path("", views.CartView.as_view(), name="cart"),
    path("add/<int:pk>/", views.AddToCartView.as_view(), name="add"),
    path("update/<int:pk>/", views.UpdateCartView.as_view(), name="update"),
    path("remove/<int:pk>/", views.RemoveCartView.as_view(), name="remove"),
]
