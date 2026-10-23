from django.contrib import admin

from apps.reviews.models import Feedback, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "customer", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating")


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("subject", "customer", "topic", "rating", "status", "created_at")
    list_filter = ("status", "topic", "rating")
    readonly_fields = ("customer", "created_at", "replied_at")
