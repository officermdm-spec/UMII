from django import forms


INPUT_CLASS = (
    "mt-1 block w-full rounded-lg border border-sky-200 bg-white px-3 py-2 text-sm "
    "text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 "
    "focus:outline-none focus:ring-2 focus:ring-brand-500/25"
)
CHECKBOX_CLASS = "h-4 w-4 rounded border-sky-300 text-brand-600 focus:ring-brand-500"
SELECT_CLASS = INPUT_CLASS
TEXTAREA_CLASS = INPUT_CLASS + " min-h-[96px]"
FILE_CLASS = (
    "mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 "
    "file:bg-sky-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700 "
    "hover:file:bg-violet-100"
)


class TailwindFormMixin:
    """Adds consistent Tailwind classes to form widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
                widget.attrs.setdefault("class", "grid gap-2 text-sm")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", CHECKBOX_CLASS)
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", FILE_CLASS)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", SELECT_CLASS)
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", TEXTAREA_CLASS)
            else:
                widget.attrs.setdefault("class", INPUT_CLASS)
