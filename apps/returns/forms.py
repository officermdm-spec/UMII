from django import forms

from apps.returns.models import ReturnItem, ReturnRequest
from config.forms import TailwindFormMixin


class ReturnRequestForm(TailwindFormMixin, forms.Form):
    reason = forms.CharField(max_length=120)
    description = forms.CharField(required=False, widget=forms.Textarea)


class ReturnItemForm(TailwindFormMixin, forms.Form):
    order_item_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1)
    selected = forms.BooleanField(required=False)


class ReturnProcessForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = ["status", "staff_notes"]


class ReturnItemConditionForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ReturnItem
        fields = ["condition"]
