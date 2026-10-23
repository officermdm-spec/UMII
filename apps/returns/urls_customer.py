from django.urls import path

from apps.returns import views

app_name = "returns_customer"

urlpatterns = [
    path("", views.CustomerReturnListView.as_view(), name="list"),
    path("order/<int:order_id>/new/", views.CustomerReturnCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CustomerReturnDetailView.as_view(), name="detail"),
]
