from django.urls import path

from apps.customers.views import (
    StaffCustomerDeleteView,
    StaffCustomerDetailView,
    StaffCustomerListView,
    StaffCustomerUpdateView,
)

app_name = "customers_staff"

urlpatterns = [
    path("", StaffCustomerListView.as_view(), name="list"),
    path("<int:pk>/", StaffCustomerDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", StaffCustomerUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", StaffCustomerDeleteView.as_view(), name="delete"),
]
