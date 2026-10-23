from django.urls import path

from apps.customers import views

app_name = "customers"

urlpatterns = [
    path("register/", views.CustomerRegisterView.as_view(), name="register"),
    path("login/", views.CustomerLoginView.as_view(), name="login"),
    path("logout/", views.CustomerLogoutView.as_view(), name="logout"),
    path("password-reset/", views.CustomerPasswordResetView.as_view(), name="password_reset"),
    path(
        "password-reset/done/",
        views.CustomerPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views.CustomerPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/complete/",
        views.CustomerPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("dashboard/", views.CustomerDashboardView.as_view(), name="dashboard"),
    path("profile/", views.ProfileUpdateView.as_view(), name="profile"),
    path("addresses/", views.AddressListView.as_view(), name="addresses"),
    path("addresses/add/", views.AddressCreateView.as_view(), name="address_create"),
    path("addresses/<int:pk>/edit/", views.AddressUpdateView.as_view(), name="address_update"),
    path("addresses/<int:pk>/delete/", views.AddressDeleteView.as_view(), name="address_delete"),
]
