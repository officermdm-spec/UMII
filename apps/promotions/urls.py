from django.urls import path

from apps.promotions import views

app_name = "promotions"

urlpatterns = [
    path("offers/", views.ProductOfferListView.as_view(), name="offer_list"),
    path("offers/add/", views.ProductOfferCreateView.as_view(), name="offer_create"),
    path("offers/<int:pk>/edit/", views.ProductOfferUpdateView.as_view(), name="offer_update"),
    path("offers/<int:pk>/delete/", views.ProductOfferDeleteView.as_view(), name="offer_delete"),
]
