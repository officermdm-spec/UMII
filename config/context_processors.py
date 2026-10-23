from django.conf import settings

from apps.accounts.permissions import can_write, is_read_only_staff, nav_modules_for_user
from apps.categories.models import Category
from apps.orders.cart import cart_summary


def storefront(request):
    whatsapp = "".join(ch for ch in str(settings.WHATSAPP_NUMBER) if ch.isdigit())
    summary = cart_summary(request)
    categories = Category.objects.filter(is_active=True, parent__isnull=True).order_by("name")
    return {
        "whatsapp_number": whatsapp,
        "support_email": settings.SUPPORT_EMAIL,
        "currency": settings.CURRENCY,
        "cart_count": summary["item_count"],
        "nav_categories": categories,
        "site_name": settings.STORE_NAME,
        "store_phone": settings.STORE_PHONE,
        "store_address": settings.STORE_ADDRESS,
    }


def staff_nav(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {
            "staff_nav_modules": [],
            "staff_can_write": False,
            "staff_is_viewer": False,
        }
    namespace = getattr(getattr(request, "resolver_match", None), "namespace", "") or ""
    items = []
    for item in nav_modules_for_user(user):
        row = dict(item)
        row["is_active"] = namespace == item.get("namespace")
        items.append(row)
    return {
        "staff_nav_modules": items,
        "staff_can_write": can_write(user),
        "staff_is_viewer": is_read_only_staff(user),
    }
