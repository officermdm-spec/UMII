from django.urls import path

from apps.purchases import views

app_name = "purchases"

urlpatterns = [
    path("", views.GRNListView.as_view(), name="list"),
    path("add/", views.GRNCreateView.as_view(), name="create"),
    path("<int:pk>/", views.GRNDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.GRNUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.GRNDeleteView.as_view(), name="delete"),
    path("<int:pk>/approve/", views.GRNApproveView.as_view(), name="approve"),
    path("<int:pk>/unapprove/", views.GRNUnapproveView.as_view(), name="unapprove"),
]
