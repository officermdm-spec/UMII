import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from apps.accounts.mixins import CustomerRequiredMixin, ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.models import User
from apps.accounts.permissions import MODULES
from apps.customers.forms import (
    AddressForm,
    CustomerLoginForm,
    CustomerPasswordResetForm,
    CustomerProfileForm,
    CustomerRegistrationForm,
    CustomerSetPasswordForm,
    StaffCustomerForm,
)
from apps.customers.models import Address, CustomerProfile
from apps.orders.cart import merge_session_cart
from apps.orders.models import Order
from apps.returns.models import ReturnRequest
from apps.reviews.models import Feedback, Review


class CustomerRegisterView(CreateView):
    form_class = CustomerRegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("customers:dashboard")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        merge_session_cart(self.request)
        messages.success(self.request, "Welcome! Your account is ready.")
        return response


class CustomerLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = CustomerLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        merge_session_cart(self.request)
        return response

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("customers:dashboard")


class CustomerLogoutView(LogoutView):
    next_page = "store:home"


class CustomerPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "emails/password_reset_email.txt"
    html_email_template_name = "emails/password_reset_email.html"
    subject_template_name = "emails/password_reset_subject.txt"
    form_class = CustomerPasswordResetForm
    success_url = reverse_lazy("customers:password_reset_done")

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.from_email = settings.DEFAULT_FROM_EMAIL
        self.extra_email_context = {
            "store_name": settings.STORE_NAME,
            "support_email": settings.SUPPORT_EMAIL,
            "store_phone": settings.STORE_PHONE,
        }

    def form_valid(self, form):
        form.save(
            use_https=self.request.is_secure() or bool(os.getenv("RENDER")),
            token_generator=self.token_generator,
            from_email=self.from_email,
            email_template_name=self.email_template_name,
            subject_template_name=self.subject_template_name,
            request=self.request,
            html_email_template_name=self.html_email_template_name,
            extra_email_context=self.extra_email_context,
        )
        return HttpResponseRedirect(self.get_success_url())


class CustomerPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["email_uses_smtp"] = bool(getattr(settings, "EMAIL_HTTP_URL", "")) or (
            "resilientsmtp" in settings.EMAIL_BACKEND.lower()
        )
        return context


class CustomerPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = CustomerSetPasswordForm
    success_url = reverse_lazy("customers:password_reset_complete")


class CustomerPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class CustomerDashboardView(CustomerRequiredMixin, TemplateView):
    template_name = "customers/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["orders"] = Order.objects.filter(customer=user)[:5]
        context["returns"] = ReturnRequest.objects.filter(customer=user)[:5]
        context["reviews"] = Review.objects.filter(customer=user)[:5]
        context["feedback_items"] = Feedback.objects.filter(customer=user)[:5]
        return context


class ProfileUpdateView(CustomerRequiredMixin, UpdateView):
    form_class = CustomerProfileForm
    template_name = "customers/profile.html"
    success_url = reverse_lazy("customers:profile")

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)


class AddressListView(CustomerRequiredMixin, ListView):
    template_name = "customers/address_list.html"
    context_object_name = "addresses"

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class AddressCreateView(CustomerRequiredMixin, CreateView):
    form_class = AddressForm
    template_name = "customers/address_form.html"
    success_url = reverse_lazy("customers:addresses")

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Address saved.")
        return super().form_valid(form)


class AddressUpdateView(CustomerRequiredMixin, UpdateView):
    form_class = AddressForm
    template_name = "customers/address_form.html"
    success_url = reverse_lazy("customers:addresses")

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class AddressDeleteView(CustomerRequiredMixin, DeleteView):
    template_name = "customers/confirm_delete.html"
    success_url = reverse_lazy("customers:addresses")

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class StaffCustomerListView(ModulePermissionMixin, ListView):
    module = MODULES.CUSTOMERS
    template_name = "staff/customers/list.html"
    context_object_name = "customers"
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.filter(user_type=User.UserType.CUSTOMER)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        return qs


class StaffCustomerDetailView(ModulePermissionMixin, TemplateView):
    module = MODULES.CUSTOMERS
    template_name = "staff/customers/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer = get_object_or_404(User, pk=self.kwargs["pk"], user_type=User.UserType.CUSTOMER)
        context["customer"] = customer
        context["orders"] = Order.objects.filter(customer=customer).select_related()[:20]
        context["addresses"] = Address.objects.filter(user=customer)
        return context


class StaffCustomerUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.CUSTOMERS
    model = User
    form_class = StaffCustomerForm
    template_name = "staff/customers/form.html"
    success_url = reverse_lazy("customers_staff:list")

    def get_queryset(self):
        return User.objects.filter(user_type=User.UserType.CUSTOMER)

    def form_valid(self, form):
        messages.success(self.request, "Customer updated.")
        return super().form_valid(form)


class StaffCustomerDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.CUSTOMERS
    model = User
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("customers_staff:list")
    delete_success_message = "Customer deactivated."
    delete_protected_message = "This customer has orders or returns and cannot be deleted. The account was left unchanged."

    def get_queryset(self):
        return User.objects.filter(user_type=User.UserType.CUSTOMER)

    def form_valid(self, form):
        if self.object.orders.exists() or self.object.return_requests.exists():
            self.object.is_active = False
            self.object.save(update_fields=["is_active"])
            messages.success(self.request, self.delete_success_message)
            return redirect(self.success_url)
        return super().form_valid(form)
