from decimal import Decimal

from django.utils import timezone

from apps.promotions.models import ProductOffer

ZERO = Decimal("0.00")
MONEY = Decimal("0.01")


def money(value):
    amount = Decimal(value or ZERO)
    if amount < 0:
        return ZERO
    return amount.quantize(MONEY)


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
        "offer": priced_offer or bxgy,
        "offer_badge": product_offer_badge(product),
    }


def quote_product_offers(items):
    products = [row["product"] for row in items if row.get("product") is not None]
    prime_product_offers(products)
    quoted = [_line_quote(row["product"], row["quantity"]) for row in items if row.get("product") is not None]

    list_subtotal = money(sum((row["line_list_total"] for row in quoted), ZERO))
    product_discount = money(sum((row["product_discount"] for row in quoted), ZERO))
    after_offer = money(sum((row["line_after_offer"] for row in quoted), ZERO))

    return {
        "items": quoted,
        "list_subtotal": list_subtotal,
        "product_discount": product_discount,
        "discount": product_discount,
        "subtotal": after_offer,
        "merchandise_total": after_offer,
    }
