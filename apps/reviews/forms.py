from django import forms

from apps.reviews.models import Feedback, Review
from config.forms import TailwindFormMixin


class ReviewForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {"rating": forms.NumberInput(attrs={"min": 1, "max": 5})}


class FeedbackForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ["topic", "rating", "subject", "message"]
        widgets = {
            "rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "message": forms.Textarea(attrs={"rows": 5}),
        }


class FeedbackReplyForm(TailwindFormMixin, forms.Form):
    status = forms.ChoiceField(choices=Feedback.Status.choices)
    staff_reply = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
