from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView, View

from apps.accounts.forms import (
    StaffLoginForm,
    StaffPasswordChangeForm,
    StaffUserForm,
    UserModulePermissionForm,
)
from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.models import User
from apps.accounts.permissions import MODULES


class StaffLoginView(LoginView):
    template_name = "accounts/staff_login.html"
    authentication_form = StaffLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("dashboard:home")


class StaffLogoutView(View):
    def post(self, request):
        logout(request)
        messages.success(request, "You have been signed out.")
        return redirect("accounts:staff_login")

    def get(self, request):
        logout(request)
        return redirect("accounts:staff_login")


class StaffUserListView(ModulePermissionMixin, ListView):
    module = MODULES.USERS
    model = User
    template_name = "staff/accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.filter(user_type=User.UserType.STAFF)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(username__icontains=q) | User.objects.filter(
                user_type=User.UserType.STAFF, email__icontains=q
            )
        return qs.distinct()


class StaffUserCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.USERS
    form_class = StaffUserForm
    template_name = "staff/accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        messages.success(self.request, "Staff user created.")
        return super().form_valid(form)


class StaffUserUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.USERS
    model = User
    form_class = StaffUserForm
    template_name = "staff/accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def get_queryset(self):
        return User.objects.filter(user_type=User.UserType.STAFF)

    def form_valid(self, form):
        messages.success(self.request, "Staff user updated.")
        return super().form_valid(form)


class StaffUserDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.USERS
    model = User
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("accounts:user_list")
    delete_success_message = "Staff user deactivated."
    delete_blocked_message = "This staff user cannot be removed."

    def get_queryset(self):
        return User.objects.filter(user_type=User.UserType.STAFF, is_superuser=False)

    def delete_is_allowed(self):
        return self.object.pk != self.request.user.pk

    def form_valid(self, form):
        self.object.is_active = False
        self.object.save(update_fields=["is_active"])
        messages.success(self.request, self.delete_success_message)
        return redirect(self.success_url)


class UserModulePermissionView(ModulePermissionMixin, FormView):
    module = MODULES.USERS
    form_class = UserModulePermissionForm
    template_name = "staff/accounts/permissions.html"
    success_url = reverse_lazy("accounts:permissions")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        user_id = self.request.GET.get("user")
        if user_id and not self.request.method == "POST":
            kwargs["selected_user"] = get_object_or_404(
                User,
                pk=user_id,
                user_type=User.UserType.STAFF,
                is_superuser=False,
            )
        return kwargs

    def form_valid(self, form):
        user = form.save()
        self.updated_user = user
        messages.success(self.request, f"Module access updated for {user}.")
        return super().form_valid(form)

    def get_success_url(self):
        return f"{self.success_url}?user={self.updated_user.pk}"
