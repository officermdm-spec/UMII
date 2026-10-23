from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.categories.forms import CategoryForm
from apps.categories.models import Category


class CategoryListView(ModulePermissionMixin, ListView):
    module = MODULES.CATEGORIES
    model = Category
    template_name = "staff/categories/list.html"
    context_object_name = "categories"
    paginate_by = 20

    def get_queryset(self):
        qs = Category.objects.select_related("parent")
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))
        return qs


class CategoryCreateView(ModulePermissionMixin, CreateView):
    module = MODULES.CATEGORIES
    form_class = CategoryForm
    template_name = "staff/categories/form.html"
    success_url = reverse_lazy("categories:list")

    def form_valid(self, form):
        messages.success(self.request, "Category created.")
        return super().form_valid(form)


class CategoryUpdateView(ModulePermissionMixin, UpdateView):
    module = MODULES.CATEGORIES
    model = Category
    form_class = CategoryForm
    template_name = "staff/categories/form.html"
    success_url = reverse_lazy("categories:list")

    def form_valid(self, form):
        messages.success(self.request, "Category updated.")
        return super().form_valid(form)


class CategoryDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.CATEGORIES
    model = Category
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("categories:list")
    delete_protected_message = "This category has products or child categories and cannot be deleted."
