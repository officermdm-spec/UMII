from django import forms

from apps.vendors.models import Vendor
from config.forms import TailwindFormMixin


class VendorForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            # "name",
            "company_name",
            "contact_person",
            "phone",
            "email",
            "address",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
        }
