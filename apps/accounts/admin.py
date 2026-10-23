from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "user_type", "is_active", "is_superuser")
    list_filter = ("user_type", "is_active", "is_staff")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Store profile", {"fields": ("user_type", "phone", "profile_image", "allowed_modules")}),
    )
