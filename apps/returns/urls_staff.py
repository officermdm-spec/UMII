from django.urls import path

from apps.returns import views

app_name = "returns_staff"

urlpatterns = [
    path("", views.StaffReturnListView.as_view(), name="list"),
    path("<int:pk>/", views.StaffReturnDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", views.StaffReturnDeleteView.as_view(), name="delete"),
    path("<int:pk>/process/", views.StaffReturnProcessView.as_view(), name="process"),
]
