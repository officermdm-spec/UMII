from django.urls import path

from apps.products import views

app_name = "store"

urlpatterns = [
    path("", views.StoreHomeView.as_view(), name="home"),
    path("shop/", views.StoreProductListView.as_view(), name="product_list"),
    path("category/<slug:slug>/", views.StoreCategoryView.as_view(), name="category"),
    path("product/<slug:slug>/", views.StoreProductDetailView.as_view(), name="product_detail"),
]
