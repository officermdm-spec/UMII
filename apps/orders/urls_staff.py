from django.urls import path

from apps.orders import views

app_name = "orders_staff"

urlpatterns = [
    path("", views.StaffOrderListView.as_view(), name="list"),
    path("<int:pk>/", views.StaffOrderDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", views.StaffOrderDeleteView.as_view(), name="delete"),
    path("<int:pk>/invoice/", views.StaffOrderInvoiceView.as_view(), name="invoice"),
    path("<int:pk>/status/", views.StaffOrderStatusView.as_view(), name="status"),
    path(
        "<int:pk>/payment-status/",
        views.StaffOrderPaymentStatusView.as_view(),
        name="payment_status",
    ),
]
