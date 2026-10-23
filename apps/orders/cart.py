from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum

from apps.orders.models import CartItem
from apps.products.models import Product
from apps.promotions.services import (
    PromotionError,
    applied_coupon_code,
    clear_applied_coupon,
    quote_promotions,
)

SESSION_CART_KEY = "cart"


def _session_cart(request):
    return request.session.setdefault(SESSION_CART_KEY, {})


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def add_to_cart(request, product, quantity=1):
    quantity = max(1, _as_int(quantity, 1))
    if request.user.is_authenticated and request.user.user_type == request.user.UserType.CUSTOMER:
        item, created = CartItem.objects.get_or_create(
            user=request.user, product=product, defaults={"quantity": quantity}
        )
        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity", "updated_at"])
        return item
    cart = _session_cart(request)
    key = str(product.pk)
    cart[key] = cart.get(key, 0) + quantity
    request.session.modified = True
    return cart


def set_quantity(request, product, quantity):
    quantity = _as_int(quantity, 0)
    if request.user.is_authenticated and request.user.user_type == request.user.UserType.CUSTOMER:
        if quantity <= 0:
            CartItem.objects.filter(user=request.user, product=product).delete()
            return
        CartItem.objects.update_or_create(
            user=request.user, product=product, defaults={"quantity": quantity}
        )
        return
    cart = _session_cart(request)
    key = str(product.pk)
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = quantity
    request.session.modified = True


def remove_from_cart(request, product):
    set_quantity(request, product, 0)


def merge_session_cart(request):
    if not request.user.is_authenticated:
        return
    cart = request.session.get(SESSION_CART_KEY, {})
    if not cart:
        return
    for product_id, qty in cart.items():
        try:
            product = Product.objects.get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            continue
        item, created = CartItem.objects.get_or_create(
            user=request.user, product=product, defaults={"quantity": int(qty)}
        )
        if not created:
            item.quantity += int(qty)
            item.save(update_fields=["quantity", "updated_at"])
    request.session[SESSION_CART_KEY] = {}
    request.session.modified = True


def cart_items(request):
    if request.user.is_authenticated and getattr(request.user, "user_type", None) == request.user.UserType.CUSTOMER:
        items = []
        for item in CartItem.objects.filter(user=request.user).select_related(
            "product", "product__category"
        ).prefetch_related("product__product_offers"):
            items.append(
                {
                    "product": item.product,
                    "quantity": item.quantity,
                    "unit_price": item.product.effective_price,
                    "list_price": item.product.selling_price,
                    "line_total": item.line_total,
                }
            )
        return items
    cart = request.session.get(SESSION_CART_KEY, {})
    products = Product.objects.filter(pk__in=cart.keys(), is_active=True).prefetch_related("product_offers")
    product_map = {str(p.pk): p for p in products}
    items = []
    for key, qty in cart.items():
        product = product_map.get(str(key))
        if not product:
            continue
        qty = _as_int(qty, 0)
        items.append(
            {
                "product": product,
                "quantity": qty,
                "unit_price": product.effective_price,
                "list_price": product.selling_price,
                "line_total": product.effective_price * qty,
            }
        )
    return items


def cart_summary(request, discount=Decimal("0.00"), coupon_code=None):
    items = cart_items(request)
    code = applied_coupon_code(request) if coupon_code is None else (coupon_code or "")
    user = getattr(request, "user", None)
    try:
        quote = quote_promotions(items, coupon_code=code or None, user=user)
    except PromotionError:
        if coupon_code is None and code:
            clear_applied_coupon(request)
        quote = quote_promotions(items, coupon_code=None, user=user)
    shipping = settings.SHIPPING_FLAT_RATE if items else Decimal("0.00")
    taxable = quote["merchandise_total"]
    tax = (taxable * settings.TAX_PERCENT / Decimal("100")).quantize(Decimal("0.01"))
    grand_total = taxable + shipping + tax
    return {
        "items": quote["items"],
        "subtotal": quote["subtotal"],
        "list_subtotal": quote["list_subtotal"],
        "product_discount": quote["product_discount"],
        "coupon_discount": quote["coupon_discount"],
        "discount": quote["coupon_discount"],
        "shipping": shipping,
        "tax": tax,
        "grand_total": grand_total,
        "item_count": sum(row["quantity"] for row in quote["items"]),
        "coupon_code": quote["coupon_code"],
        "coupon": quote["coupon"],
        "allow_stack": quote["allow_stack"],
    }


def clear_cart(request):
    if request.user.is_authenticated:
        CartItem.objects.filter(user=request.user).delete()
    request.session[SESSION_CART_KEY] = {}
    request.session.modified = True
