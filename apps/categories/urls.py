from django.urls import path

from apps.categories import views

app_name = "categories"

urlpatterns = [
    path("", views.CategoryListView.as_view(), name="list"),
    path("add/", views.CategoryCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="delete"),
]
