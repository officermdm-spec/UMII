"""Product-level Code 128 barcodes. The stored value is the source of truth."""

from io import BytesIO

from django.db import transaction
from django.db.models import Max

BARCODE_PREFIX = "FP"
BARCODE_DIGITS = 10
BARCODE_FORMAT = "code128"


class BarcodeLookupError(Exception):
    def __init__(self, message, code="unknown"):
        self.code = code
        super().__init__(message)


def normalize_barcode(value):
    return "".join(str(value or "").split()).upper()


def allocate_unique_barcode():
    """Transaction-safe sequential Code 128 value: FP + 10 digits."""
    from apps.products.models import Product

    with transaction.atomic():
        Product.objects.select_for_update().filter(barcode__startswith=BARCODE_PREFIX).order_by("pk")[:1]
        last = (
            Product.objects.filter(barcode__startswith=BARCODE_PREFIX)
            .aggregate(m=Max("barcode"))
            .get("m")
        )
        suffix = (last or "")[len(BARCODE_PREFIX) :]
        n = int(suffix) + 1 if suffix.isdigit() else 1
        for _ in range(1000):
            candidate = f"{BARCODE_PREFIX}{n:0{BARCODE_DIGITS}d}"
            if not Product.objects.filter(barcode=candidate).exists():
                return candidate
            n += 1
    raise RuntimeError("Could not allocate a unique product barcode.")


def render_barcode_png(value):
    """High-resolution Code 128 PNG generated from the stored value."""
    from barcode import Code128
    from barcode.writer import ImageWriter

    text = normalize_barcode(value)
    if not text:
        raise BarcodeLookupError("Barcode value is required.", "blank")
    options = {
        "module_width": 0.35,
        "module_height": 18.0,
        "quiet_zone": 6.5,
        "font_size": 10,
        "text_distance": 5.0,
        "write_text": True,
        "dpi": 300,
    }
    buffer = BytesIO()
    try:
        Code128(text, writer=ImageWriter()).write(buffer, options=options)
    except Exception:
        buffer = BytesIO()
        options["write_text"] = False
        Code128(text, writer=ImageWriter()).write(buffer, options=options)
    return buffer.getvalue()


def get_product_by_barcode(raw, *, active_only=True):
    """Reusable product lookup. Never use the scanned value for prices."""
    from apps.products.models import Product

    value = normalize_barcode(raw)
    if not value:
        raise BarcodeLookupError("Enter or scan a barcode.", "blank")
    qs = Product.objects.select_related("category", "vendor", "brand")
    matches = list(qs.filter(barcode__iexact=value)[:2])
    if not matches:
        raise BarcodeLookupError("Unknown barcode.", "unknown")
    if len(matches) > 1:
        raise BarcodeLookupError("Duplicate barcode detected. Contact an administrator.", "duplicate")
    product = matches[0]
    if active_only and not product.is_active:
        raise BarcodeLookupError("This product is inactive.", "inactive")
    return product


def ensure_product_barcode(product):
    if product.barcode:
        return product.barcode
    product.barcode = allocate_unique_barcode()
    return product.barcode
