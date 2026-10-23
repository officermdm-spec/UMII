from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.StaffLoginView.as_view(), name="staff_login"),
    path("logout/", views.StaffLogoutView.as_view(), name="staff_logout"),
    path("users/", views.StaffUserListView.as_view(), name="user_list"),
    path("users/add/", views.StaffUserCreateView.as_view(), name="user_create"),
    path("users/<int:pk>/edit/", views.StaffUserUpdateView.as_view(), name="user_update"),
    path("users/<int:pk>/delete/", views.StaffUserDeleteView.as_view(), name="user_delete"),
    path("permissions/", views.UserModulePermissionView.as_view(), name="permissions"),
]
