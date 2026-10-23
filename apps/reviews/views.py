from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, View

from apps.accounts.mixins import CustomerRequiredMixin, ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES
from apps.orders.models import Order
from apps.reviews.forms import FeedbackForm, FeedbackReplyForm, ReviewForm
from apps.reviews.models import Feedback, Review


class ReviewCreateView(CustomerRequiredMixin, CreateView):
    form_class = ReviewForm
    template_name = "customers/review_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.order = get_object_or_404(Order, pk=kwargs["order_id"], customer=request.user)
        if self.order.status not in {Order.Status.DELIVERED, Order.Status.RECEIVED}:
            messages.error(request, "You can review products after delivery.")
            return redirect("orders_customer:detail", pk=self.order.pk)
        self.item = get_object_or_404(self.order.items, pk=kwargs["item_id"])
        if Review.objects.filter(
            customer=request.user, product=self.item.product, order=self.order
        ).exists():
            messages.info(request, "You already reviewed this product for this order.")
            return redirect("orders_customer:detail", pk=self.order.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        review = form.save(commit=False)
        review.customer = self.request.user
        review.product = self.item.product
        review.order = self.order
        review.save()
        messages.success(self.request, "Review submitted and waiting for approval.")
        return redirect("orders_customer:detail", pk=self.order.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["order"] = self.order
        context["item"] = self.item
        return context


class FeedbackCreateView(CustomerRequiredMixin, CreateView):
    form_class = FeedbackForm
    template_name = "customers/feedback_form.html"
    success_url = reverse_lazy("reviews_customer:feedback_list")

    def form_valid(self, form):
        form.instance.customer = self.request.user
        messages.success(self.request, "Thanks — we received your feedback.")
        return super().form_valid(form)


class CustomerFeedbackListView(CustomerRequiredMixin, ListView):
    template_name = "customers/feedback_list.html"
    context_object_name = "feedback_list"

    def get_queryset(self):
        return Feedback.objects.filter(customer=self.request.user)


class StaffReviewListView(ModulePermissionMixin, ListView):
    module = MODULES.REVIEWS
    model = Review
    template_name = "staff/reviews/list.html"
    context_object_name = "reviews"
    paginate_by = 20

    def get_queryset(self):
        qs = Review.objects.select_related("customer", "product", "order")
        status = self.request.GET.get("status")
        if status == "pending":
            qs = qs.filter(is_approved__isnull=True)
        elif status == "approved":
            qs = qs.filter(is_approved=True)
        elif status == "rejected":
            qs = qs.filter(is_approved=False)
        return qs


class StaffReviewDeleteView(SafeDeleteMixin, ModulePermissionMixin, DeleteView):
    module = MODULES.REVIEWS
    model = Review
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("reviews_staff:list")
    delete_success_message = "Review deleted."


class StaffReviewModerateView(ModulePermissionMixin, View):
    module = MODULES.REVIEWS
    def post(self, request, pk):
        review = get_object_or_404(Review, pk=pk)
        action = request.POST.get("action")
        review.is_approved = action == "approve"
        review.save(update_fields=["is_approved", "updated_at"])
        messages.success(request, "Review updated.")
        return redirect("reviews_staff:list")


class StaffFeedbackListView(ModulePermissionMixin, ListView):
    module = MODULES.REVIEWS
    model = Feedback
    template_name = "staff/reviews/feedback_list.html"
    context_object_name = "feedback_list"
    paginate_by = 20

    def get_queryset(self):
        qs = Feedback.objects.select_related("customer", "replied_by")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_filter"] = self.request.GET.get("status", "")
        context["statuses"] = Feedback.Status.choices
        return context


class StaffFeedbackReplyView(ModulePermissionMixin, View):
    module = MODULES.REVIEWS

    def post(self, request, pk):
        item = get_object_or_404(Feedback, pk=pk)
        form = FeedbackReplyForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Could not save the reply.")
            return redirect("reviews_staff:feedback")
        reply = form.cleaned_data.get("staff_reply", "").strip()
        status = form.cleaned_data["status"]
        if reply:
            item.mark_replied(request.user, reply, status=status)
        else:
            item.status = status
            item.save(update_fields=["status"])
        messages.success(request, "Feedback updated.")
        return redirect("reviews_staff:feedback")
