from django.urls import path

from apps.reviews import views

app_name = "reviews_customer"

urlpatterns = [
    path("order/<int:order_id>/item/<int:item_id>/", views.ReviewCreateView.as_view(), name="create"),
    path("feedback/", views.FeedbackCreateView.as_view(), name="feedback"),
    path("feedback/history/", views.CustomerFeedbackListView.as_view(), name="feedback_list"),
]
