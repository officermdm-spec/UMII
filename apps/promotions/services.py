from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.promotions.models import ProductOffer, Promotion, PromotionUsage

ZERO = Decimal("0.00")
MONEY = Decimal("0.01")
APPLIED_COUPON_SESSION_KEY = "applied_coupon"


class PromotionError(Exception):
    pass


def money(value):
    amount = Decimal(value or ZERO)
    if amount < 0:
        return ZERO
    return amount.quantize(MONEY)


def coupon_stacking_allowed():
    return bool(getattr(settings, "ALLOW_COUPON_WITH_PRODUCT_OFFER", False))


def live_promotions():
    """Coupons that should appear on the storefront."""
    now = timezone.now()
    return (
        Promotion.objects.filter(
            is_active=True,
            show_on_website=True,
            start_date__lte=now,
            end_date__gte=now,
            code__isnull=False,
        )
        .exclude(code="")
        .prefetch_related("products")
    )


def live_product_offers():
    now = timezone.now()
    return (
        ProductOffer.objects.filter(
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
        )
        .prefetch_related("products")
    )


def get_coupon_by_code(code=None):
    if not code:
        return None
    return (
        Promotion.objects.filter(code__iexact=str(code).strip())
        .exclude(code="")
        .prefetch_related("products")
        .first()
    )


def get_active_promotion(code=None):
    if not code:
        return None
    return live_promotions().filter(code__iexact=str(code).strip()).first() or get_coupon_by_code(code)


def _selected_product_ids(promotion):
    return {item.pk for item in promotion.products.all()}


def _line_is_eligible(product, promotion, *, has_product_offer=False, allow_stack=True):
    if has_product_offer and not allow_stack:
        return False
    selected_ids = _selected_product_ids(promotion)
    if selected_ids:
        return product.pk in selected_ids or product.variant_parent_id in selected_ids
    if promotion.apply_to == Promotion.ApplyTo.ALL:
        return True
    return False


def _live_offers_for_product(product):
    cached = getattr(product, "_live_product_offers", None)
    if cached is not None:
        return cached
    now = timezone.now()
    prefetch = getattr(product, "_prefetched_objects_cache", {})
    if "product_offers" in prefetch:
        offers = [
            offer
            for offer in product.product_offers.all()
            if offer.is_active and offer.start_date <= now <= offer.end_date
        ]
    else:
        offers = list(
            product.product_offers.filter(
                is_active=True, start_date__lte=now, end_date__gte=now
            )
        )
    if product.variant_parent_id:
        parent = product.variant_parent
        parent_prefetch = getattr(parent, "_prefetched_objects_cache", {})
        if "product_offers" in parent_prefetch:
            offers.extend(
                offer
                for offer in parent.product_offers.all()
                if offer.is_active and offer.start_date <= now <= offer.end_date
            )
        else:
            offers.extend(
                parent.product_offers.filter(
                    is_active=True, start_date__lte=now, end_date__gte=now
                )
            )
        offers = list({offer.pk: offer for offer in offers}.values())
    product._live_product_offers = offers
    return offers


def prime_product_offers(products):
    products = [product for product in products if product is not None]
    if not products:
        return
    offers = list(live_product_offers())
    by_id = {product.pk: [] for product in products}
    for offer in offers:
        for product in offer.products.all():
            if product.pk in by_id:
                by_id[product.pk].append(offer)
            for candidate in products:
                if candidate.variant_parent_id == product.pk:
                    by_id[candidate.pk].append(offer)
    for product in products:
        product._live_product_offers = by_id.get(product.pk, [])


def _offer_unit_price(product, offer):
    list_price = product.selling_price
    if offer.offer_type == ProductOffer.OfferType.PERCENTAGE:
        return money(list_price * (Decimal("100") - offer.value) / Decimal("100"))
    if offer.offer_type == ProductOffer.OfferType.FIXED:
        return money(list_price - offer.value)
    return list_price


def best_price_offer(product):
    priced = [
        offer
        for offer in _live_offers_for_product(product)
        if offer.offer_type != ProductOffer.OfferType.BUY_X_GET_Y
    ]
    if not priced:
        return None
    return min(priced, key=lambda offer: _offer_unit_price(product, offer))


def best_bxgy_offer(product):
    offers = [
        offer
        for offer in _live_offers_for_product(product)
        if offer.offer_type == ProductOffer.OfferType.BUY_X_GET_Y and offer.buy_qty and offer.get_qty
    ]
    if not offers:
        return None
    return min(offers, key=lambda offer: (offer.buy_qty, -offer.get_qty, offer.pk))


def unit_price_for(product):
    catalog = money(product.selling_price - product.discount_amount)
    offer = best_price_offer(product)
    candidates = [product.selling_price, catalog]
    if offer:
        candidates.append(_offer_unit_price(product, offer))
    return money(min(candidates))


def product_offer_badge(product):
    priced = best_price_offer(product)
    bxgy = best_bxgy_offer(product)
    sale_price = unit_price_for(product)
    if priced and sale_price < product.selling_price:
        saved = product.selling_price - sale_price
        percent = (saved * Decimal("100") / product.selling_price).quantize(Decimal("1"))
        return f"-{percent}% OFF"
    if product.discount_percent and product.discount_percent > 0 and sale_price < product.selling_price:
        return f"-{product.discount_percent.quantize(Decimal('1'))}% OFF"
    if bxgy:
        return f"Buy {bxgy.buy_qty} Get {bxgy.get_qty}"
    return ""


def _assert_coupon_usable(promotion, user):
    if promotion is None:
        raise PromotionError("Invalid coupon code.")
    now = timezone.now()
    if not promotion.is_active:
        raise PromotionError("This coupon is disabled.")
    if promotion.start_date > now:
        raise PromotionError("This coupon is not valid yet.")
    if promotion.end_date < now:
        raise PromotionError("This coupon has expired.")
    if promotion.usage_limit is not None and promotion.used_count >= promotion.usage_limit:
        raise PromotionError("This coupon has reached its usage limit.")
    if user is not None and getattr(user, "is_authenticated", False):
        per_customer = promotion.usage_limit_per_customer
        if per_customer:
            used = PromotionUsage.objects.filter(promotion=promotion, customer=user).count()
            if used >= per_customer:
                raise PromotionError("You have already used this coupon the allowed number of times.")


def allocate_coupon_discounts(promotion, items, subtotal, *, allow_stack=True):
    """Split a coupon across eligible lines. Amounts are always computed here, never trusted from the client."""
    if subtotal < promotion.min_order_amount:
        raise PromotionError(
            f"Minimum order amount for this coupon is Rs. {promotion.min_order_amount}."
        )
    amounts = []
    eligible_total = ZERO
    for row in items:
        line_total = Decimal(row["line_total"])
        eligible = _line_is_eligible(
            row["product"],
            promotion,
            has_product_offer=bool(row.get("has_product_offer")),
            allow_stack=allow_stack,
        )
        if eligible:
            eligible_total += line_total
            if promotion.discount_type == Promotion.DiscountType.PERCENTAGE:
                amounts.append(money((line_total * promotion.value) / Decimal("100")))
            else:
                amounts.append(ZERO)
        else:
            amounts.append(ZERO)
    if eligible_total <= 0:
        if any(row.get("has_product_offer") for row in items) and not allow_stack:
            raise PromotionError("This coupon cannot be combined with a product offer.")
        raise PromotionError("This coupon does not apply to the items in your cart.")

    if promotion.discount_type == Promotion.DiscountType.FIXED:
        remaining = min(promotion.value, eligible_total)
        leftover = remaining
        eligible_indexes = [
            index
            for index, row in enumerate(items)
            if _line_is_eligible(
                row["product"],
                promotion,
                has_product_offer=bool(row.get("has_product_offer")),
                allow_stack=allow_stack,
            )
        ]
        for position, index in enumerate(eligible_indexes):
            if position == len(eligible_indexes) - 1:
                amounts[index] = money(leftover)
            else:
                share = money(items[index]["line_total"] / eligible_total * remaining)
                amounts[index] = share
                leftover -= share

    total = sum(amounts, ZERO)
    if promotion.max_discount is not None and total > promotion.max_discount:
        factor = promotion.max_discount / total
        scaled = [money(amount * factor) for amount in amounts]
        drift = promotion.max_discount - sum(scaled, ZERO)
        for index in range(len(scaled) - 1, -1, -1):
            if scaled[index] > 0:
                scaled[index] = money(scaled[index] + drift)
                break
        amounts = scaled
    return amounts


def calculate_discount(promotion, items, subtotal, *, allow_stack=True):
    return sum(allocate_coupon_discounts(promotion, items, subtotal, allow_stack=allow_stack), ZERO)


def validate_promotion(promotion, user, items, subtotal, *, allow_stack=True):
    _assert_coupon_usable(promotion, user)
    return calculate_discount(promotion, items, subtotal, allow_stack=allow_stack)


def _line_quote(product, quantity):
    qty = max(int(quantity or 0), 0)
    list_price = product.selling_price
    unit_price = unit_price_for(product)
    bxgy = best_bxgy_offer(product)
    priced_offer = best_price_offer(product)
    paid_qty = qty
    if bxgy and bxgy.buy_qty and qty:
        group = bxgy.buy_qty + bxgy.get_qty
        if group:
            free = (qty // group) * bxgy.get_qty
            paid_qty = qty - free
    line_list = money(list_price * qty)
    line_after_offer = money(unit_price * paid_qty)
    product_discount = money(line_list - line_after_offer)
    return {
        "product": product,
        "quantity": qty,
        "list_price": list_price,
        "unit_price": unit_price,
        "line_list_total": line_list,
        "line_after_offer": line_after_offer,
        "line_total": line_after_offer,
        "product_discount": product_discount,
        "has_product_offer": product_discount > 0,
        "offer": priced_offer or bxgy,
        "offer_badge": product_offer_badge(product),
        "coupon_discount": ZERO,
        "promo_percent": ZERO,
    }


def quote_promotions(items, *, coupon_code=None, user=None, allow_stack=None):
    """Single backend quote for product offers + optional coupon. Never trusts client amounts."""
    if allow_stack is None:
        allow_stack = coupon_stacking_allowed()
    products = [row["product"] for row in items if row.get("product") is not None]
    prime_product_offers(products)
    quoted = [_line_quote(row["product"], row["quantity"]) for row in items if row.get("product") is not None]

    list_subtotal = money(sum((row["line_list_total"] for row in quoted), ZERO))
    product_discount = money(sum((row["product_discount"] for row in quoted), ZERO))
    after_offer = money(sum((row["line_after_offer"] for row in quoted), ZERO))

    coupon = None
    coupon_total = ZERO
    code = (coupon_code or "").strip()
    if code:
        coupon = get_coupon_by_code(code)
        alloc_items = [
            {
                "product": row["product"],
                "quantity": row["quantity"],
                "line_total": row["line_after_offer"],
                "has_product_offer": row["has_product_offer"],
            }
            for row in quoted
        ]
        amounts = []
        try:
            _assert_coupon_usable(coupon, user)
            amounts = allocate_coupon_discounts(
                coupon, alloc_items, after_offer, allow_stack=allow_stack
            )
        except PromotionError:
            raise
        for row, amount in zip(quoted, amounts):
            capped = money(min(amount, row["line_after_offer"]))
            row["coupon_discount"] = capped
            if capped > 0 and coupon.discount_type == Promotion.DiscountType.PERCENTAGE:
                row["promo_percent"] = coupon.value
            row["line_total"] = money(row["line_after_offer"] - capped)
        coupon_total = money(sum((row["coupon_discount"] for row in quoted), ZERO))

    merchandise = money(after_offer - coupon_total)
    return {
        "items": quoted,
        "list_subtotal": list_subtotal,
        "product_discount": product_discount,
        "coupon_discount": coupon_total,
        "discount": money(product_discount + coupon_total),
        "subtotal": after_offer,
        "merchandise_total": merchandise,
        "coupon": coupon,
        "coupon_code": coupon.code if coupon else "",
        "allow_stack": allow_stack,
    }


def set_applied_coupon(request, code):
    request.session[APPLIED_COUPON_SESSION_KEY] = (code or "").strip().upper()
    request.session.modified = True


def clear_applied_coupon(request):
    request.session.pop(APPLIED_COUPON_SESSION_KEY, None)
    request.session.modified = True


def applied_coupon_code(request):
    return (request.session.get(APPLIED_COUPON_SESSION_KEY) or "").strip()


def restore_coupon_usage(order):
    usages = list(PromotionUsage.objects.filter(order=order).select_related("promotion"))
    if not usages:
        return
    from django.db.models import F

    for usage in usages:
        Promotion.objects.filter(pk=usage.promotion_id, used_count__gt=0).update(
            used_count=F("used_count") - 1
        )
    PromotionUsage.objects.filter(order=order).delete()
