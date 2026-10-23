from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="list"),
    path("methods/", views.PaymentMethodListView.as_view(), name="methods"),
    path("methods/add/", views.PaymentMethodCreateView.as_view(), name="method_create"),
    path("methods/<int:pk>/edit/", views.PaymentMethodUpdateView.as_view(), name="method_update"),
    path("methods/<int:pk>/delete/", views.PaymentMethodDeleteView.as_view(), name="method_delete"),
    path("<int:pk>/", views.PaymentDetailView.as_view(), name="detail"),
    path("<int:pk>/status/", views.PaymentStatusUpdateView.as_view(), name="status"),
    path("<int:pk>/paid/", views.PaymentMarkPaidView.as_view(), name="mark_paid"),
    path("<int:pk>/failed/", views.PaymentMarkFailedView.as_view(), name="mark_failed"),
]
