from django.urls import path

from apps.orders import views

app_name = "orders_customer"

urlpatterns = [
    path("track/", views.CustomerOrderTrackView.as_view(), name="track"),
    path("", views.CustomerOrderListView.as_view(), name="list"),
    path("<int:pk>/", views.CustomerOrderDetailView.as_view(), name="detail"),
    path("<int:pk>/invoice/", views.CustomerOrderInvoiceView.as_view(), name="invoice"),
    path("<int:pk>/cancel/", views.CustomerCancelOrderView.as_view(), name="cancel"),
    path("<int:pk>/received/", views.CustomerReceiveOrderView.as_view(), name="received"),
]
