from django.shortcuts import resolve_url
from django.utils import timezone


def next_document_number(model, field, prefix):
    """Return the next document number for the given model/field, e.g. ORD-20260911-0001."""
    today = timezone.localdate().strftime("%Y%m%d")
    base = f"{prefix}-{today}-"
    last = (
        model.objects.filter(**{f"{field}__startswith": base})
        .order_by(f"-{field}")
        .values_list(field, flat=True)
        .first()
    )
    if last:
        try:
            seq = int(str(last).split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{base}{seq:04d}"


def safe_internal_url(candidate, fallback):
    """Allow only same-origin relative paths. Blocks open redirects."""
    url = (candidate or "").strip()
    if url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return resolve_url(fallback)
