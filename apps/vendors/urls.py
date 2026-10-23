from django.urls import path

from apps.vendors import views

app_name = "vendors"

urlpatterns = [
    path("", views.VendorListView.as_view(), name="list"),
    path("add/", views.VendorCreateView.as_view(), name="create"),
    path("<int:pk>/", views.VendorDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.VendorUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.VendorDeleteView.as_view(), name="delete"),
]
