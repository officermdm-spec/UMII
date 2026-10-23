from django.contrib.admin import ModelAdmin, register

from apps.categories.models import Category


@register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name", "parent", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("is_active",)
