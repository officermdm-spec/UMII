from django import forms

from apps.categories.models import Category
from config.forms import TailwindFormMixin


class CategoryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "description", "image", "parent", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(parent__isnull=True)
        self.fields["slug"].required = False
