from django.urls import path

from apps.reviews import views

app_name = "reviews_staff"

urlpatterns = [
    path("", views.StaffReviewListView.as_view(), name="list"),
    path("<int:pk>/delete/", views.StaffReviewDeleteView.as_view(), name="delete"),
    path("<int:pk>/moderate/", views.StaffReviewModerateView.as_view(), name="moderate"),
    path("feedback/", views.StaffFeedbackListView.as_view(), name="feedback"),
    path("feedback/<int:pk>/reply/", views.StaffFeedbackReplyView.as_view(), name="feedback_reply"),
]
