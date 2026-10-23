from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import deletion
from django.shortcuts import redirect
from django.urls import reverse

from apps.accounts.permissions import (
    SAFE_HTTP_METHODS,
    can_write,
    has_module_permission,
    is_read_only_staff,
    is_staff_user,
)


class StaffRequiredMixin(AccessMixin):
    """Requires an authenticated staff user or superuser."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:staff_login')}?next={request.get_full_path()}")
        if not is_staff_user(request.user):
            raise PermissionDenied("Staff access only.")
        return super().dispatch(request, *args, **kwargs)


class ModulePermissionMixin(AccessMixin):
    module = None
    write_required = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('accounts:staff_login')}?next={request.get_full_path()}")
        if not is_staff_user(request.user):
            raise PermissionDenied("Staff access only.")
        if not has_module_permission(request.user, self.module):
            raise PermissionDenied("You do not have permission to access this module.")
        mutating = request.method not in SAFE_HTTP_METHODS
        if (mutating or self.write_required) and is_read_only_staff(request.user):
            raise PermissionDenied("Read-only accounts cannot change data.")
        return super().dispatch(request, *args, **kwargs)


class SafeDeleteMixin:
    delete_success_message = "Record deleted."
    delete_protected_message = "This record is linked to other data and cannot be deleted."
    delete_blocked_message = "This record cannot be deleted in its current state."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("object_label", str(self.object))
        context.setdefault("cancel_url", self.success_url)
        return context

    def delete_is_allowed(self):
        return True

    def form_valid(self, form):
        if not can_write(self.request.user):
            raise PermissionDenied("Read-only accounts cannot change data.")
        if not self.delete_is_allowed():
            messages.error(self.request, self.delete_blocked_message)
            return redirect(self.success_url)
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except deletion.ProtectedError:
            messages.error(self.request, self.delete_protected_message)
            return redirect(self.success_url)
        messages.success(self.request, self.delete_success_message)
        return response


class CustomerRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('customers:login')}?next={request.get_full_path()}")
        return super().dispatch(request, *args, **kwargs)
