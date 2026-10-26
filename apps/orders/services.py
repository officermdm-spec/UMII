from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.inventory.models import Inventory, StockTransaction
from apps.inventory.services import (
    StockError,
    allocate_stock,
    available_stock,
    get_default_warehouse,
    record_stock_transaction,
)
from apps.orders.cart import cart_items, clear_cart
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.payments.models import PaymentMethod
from apps.payments.services import create_payment_for_order
from apps.promotions.models import Promotion, PromotionUsage
from apps.promotions.services import (
    applied_coupon_code,
    clear_applied_coupon,
    money,
    quote_promotions,
    restore_coupon_usage,
)
from config.utils import next_document_number


class OrderError(Exception):
    pass


STATUS_FLOW = {
    Order.Status.PENDING: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.CONFIRMED: {Order.Status.PROCESSING, Order.Status.CANCELLED},
    Order.Status.PROCESSING: {Order.Status.DELIVERED, Order.Status.CANCELLED},
    # Legacy statuses kept so old orders can still move forward.
    Order.Status.IN_PROGRESS: {Order.Status.DELIVERED, Order.Status.CANCELLED},
    Order.Status.ON_WAY: {Order.Status.DELIVERED, Order.Status.CANCELLED},
    Order.Status.DELIVERED: {Order.Status.RECEIVED, Order.Status.RETURN_REQUESTED},
    Order.Status.RECEIVED: {Order.Status.RETURN_REQUESTED},
    Order.Status.RETURN_REQUESTED: {Order.Status.RETURNED},
    Order.Status.CANCELLED: set(),
    Order.Status.RETURNED: set(),
}

HIDDEN_TRACKER_STATUSES = {Order.Status.IN_PROGRESS, Order.Status.ON_WAY}

# Happy-path journey shown on the visual tracker.
FULFILLMENT_STEPS = [
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PROCESSING,
    Order.Status.DELIVERED,
]

RETURN_STEPS = [
    Order.Status.DELIVERED,
    Order.Status.RETURN_REQUESTED,
    Order.Status.RETURNED,
]

STATUS_HINTS = {
    Order.Status.PENDING: "Order placed — waiting for confirmation",
    Order.Status.CONFIRMED: "Order confirmed by our team",
    Order.Status.PROCESSING: "Items are being prepared at the warehouse",
    Order.Status.IN_PROGRESS: "Items are being prepared at the warehouse",
    Order.Status.ON_WAY: "Items are being prepared at the warehouse",
    Order.Status.DELIVERED: "Delivered successfully",
    Order.Status.RECEIVED: "You confirmed the order was received",
    Order.Status.CANCELLED: "This order was cancelled",
    Order.Status.RETURN_REQUESTED: "Return request is under review",
    Order.Status.RETURNED: "Return completed",
}

STATUS_LABELS = dict(Order.Status.choices)


def build_order_tracker(order):
    """Build a customer/staff-facing progress tracker for an order."""
    history = list(order.status_history.all())
    first_seen = {}
    for row in history:
        first_seen.setdefault(row.status, row.created_at)

    current = order.status
    labels = STATUS_LABELS
    if current in HIDDEN_TRACKER_STATUSES:
        current = Order.Status.PROCESSING

    if current == Order.Status.CANCELLED:
        # Freeze progress at the last fulfillment step before cancel.
        reached = Order.Status.PENDING
        for row in history:
            mapped = row.status
            if mapped in HIDDEN_TRACKER_STATUSES:
                mapped = Order.Status.PROCESSING
            if mapped in FULFILLMENT_STEPS:
                reached = mapped
            if row.status == Order.Status.CANCELLED:
                break
        reached_idx = FULFILLMENT_STEPS.index(reached)
        steps = []
        for idx, key in enumerate(FULFILLMENT_STEPS):
            if idx < reached_idx:
                state = "done"
            elif idx == reached_idx:
                state = "done"
            else:
                state = "skipped"
            steps.append(
                {
                    "key": key,
                    "label": labels[key],
                    "state": state,
                    "at": first_seen.get(key),
                    "hint": STATUS_HINTS[key],
                }
            )
        steps.append(
            {
                "key": Order.Status.CANCELLED,
                "label": labels[Order.Status.CANCELLED],
                "state": "cancelled",
                "at": first_seen.get(Order.Status.CANCELLED) or order.updated_at,
                "hint": STATUS_HINTS[Order.Status.CANCELLED],
            }
        )
        return {
            "mode": "cancelled",
            "current": current,
            "current_label": labels[current],
            "current_hint": STATUS_HINTS[current],
            "progress_percent": 100,
            "steps": steps,
            "history": history,
        }

    if current in {Order.Status.RETURN_REQUESTED, Order.Status.RETURNED}:
        steps = []
        current_idx = RETURN_STEPS.index(current)
        for idx, key in enumerate(RETURN_STEPS):
            if idx < current_idx:
                state = "done"
            elif idx == current_idx:
                state = "current"
            else:
                state = "upcoming"
            steps.append(
                {
                    "key": key,
                    "label": labels[key],
                    "state": state,
                    "at": first_seen.get(key),
                    "hint": STATUS_HINTS[key],
                }
            )
        return {
            "mode": "return",
            "current": current,
            "current_label": labels[current],
            "current_hint": STATUS_HINTS[current],
            "progress_percent": int(round((current_idx + 1) / len(RETURN_STEPS) * 100)),
            "steps": steps,
            "history": history,
        }

    # Normal fulfillment path (pending → delivered), plus optional received.
    tracker_status = current
    if tracker_status == Order.Status.RECEIVED:
        tracker_status = Order.Status.DELIVERED
    if tracker_status not in FULFILLMENT_STEPS:
        tracker_status = Order.Status.PENDING
    current_idx = FULFILLMENT_STEPS.index(tracker_status)
    steps = []
    for idx, key in enumerate(FULFILLMENT_STEPS):
        if idx < current_idx:
            state = "done"
        elif idx == current_idx:
            state = "done" if current == Order.Status.RECEIVED else "current"
        else:
            state = "upcoming"
        steps.append(
            {
                "key": key,
                "label": labels[key],
                "state": state,
                "at": first_seen.get(key),
                "hint": STATUS_HINTS[key],
            }
        )
    if current in {Order.Status.DELIVERED, Order.Status.RECEIVED}:
        steps.append(
            {
                "key": Order.Status.RECEIVED,
                "label": labels[Order.Status.RECEIVED],
                "state": "current" if current == Order.Status.RECEIVED else "upcoming",
                "at": first_seen.get(Order.Status.RECEIVED),
                "hint": "Optional — confirm you received the order",
                "optional": True,
            }
        )
    progress_base = current_idx + 1
    total = len(FULFILLMENT_STEPS)
    if current in {Order.Status.DELIVERED, Order.Status.RECEIVED}:
        total += 1
    if current == Order.Status.RECEIVED:
        progress_base = total
    return {
        "mode": "fulfillment",
        "current": current,
        "current_label": labels[current],
        "current_hint": STATUS_HINTS[current],
        "progress_percent": int(round(progress_base / total * 100)),
        "steps": steps,
        "history": history,
    }


def _copy_address(prefix, address):
    return {
        f"{prefix}_full_name": address.full_name,
        f"{prefix}_phone": address.phone,
        f"{prefix}_address": address.address,
        f"{prefix}_city": address.city,
        f"{prefix}_area": address.area,
        f"{prefix}_postal_code": address.postal_code,
    }


def add_status_history(order, status, user=None, note=""):
    OrderStatusHistory.objects.create(
        order=order, status=status, changed_by=user, note=note
    )


SALE_STATUSES = {
    Order.Status.CONFIRMED,
    Order.Status.PROCESSING,
    Order.Status.IN_PROGRESS,
    Order.Status.ON_WAY,
    Order.Status.DELIVERED,
    Order.Status.RECEIVED,
}

PRE_DELIVERY_STATUSES = {
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PROCESSING,
    Order.Status.IN_PROGRESS,
    Order.Status.ON_WAY,
}


def _has_stock_txn(order, txn_type):
    return StockTransaction.objects.filter(
        reference=order.order_number, transaction_type=txn_type
    ).exists()


def _iter_stock_items(order):
    for item in order.items.select_related("product"):
        if item.product_id:
            yield item


def _order_warehouse(order):
    return order.fulfillment_warehouse or get_default_warehouse()


def _order_txns(order, txn_type):
    return list(
        StockTransaction.objects.filter(
            reference=order.order_number, transaction_type=txn_type
        ).select_related("product", "warehouse")
    )


def _post_sale(order, warehouse, user):
    if not _has_stock_txn(order, StockTransaction.Type.SALE):
        reserves = _order_txns(order, StockTransaction.Type.RESERVE)
        if reserves:
            for txn in reserves:
                record_stock_transaction(
                    product=txn.product,
                    warehouse=txn.warehouse,
                    quantity=-txn.quantity,
                    transaction_type=StockTransaction.Type.SALE,
                    reference=order.order_number,
                    user=user,
                    notes="Converted reserved stock to sale",
                    costing_mode="none",
                )
        else:
            for item in _iter_stock_items(order):
                record_stock_transaction(
                    product=item.product,
                    warehouse=warehouse,
                    quantity=-item.quantity,
                    transaction_type=StockTransaction.Type.SALE,
                    reference=order.order_number,
                    user=user,
                    notes="Converted reserved stock to sale",
                    costing_mode="none",
                )
        from apps.inventory.costing import consume_order_cogs

        consume_order_cogs(order, warehouse)
    from apps.accounting.services import post_sale_event

    post_sale_event(order, user)


def _release_reserve(order, warehouse, user):
    if not _has_stock_txn(order, StockTransaction.Type.RESERVE):
        return
    if _has_stock_txn(order, StockTransaction.Type.RELEASE):
        return
    reserves = _order_txns(order, StockTransaction.Type.RESERVE)
    if reserves:
        for txn in reserves:
            record_stock_transaction(
                product=txn.product,
                warehouse=txn.warehouse,
                quantity=txn.quantity,
                transaction_type=StockTransaction.Type.RELEASE,
                reference=order.order_number,
                user=user,
                notes="Released reserved stock on cancel",
            )
        return
    for item in _iter_stock_items(order):
        record_stock_transaction(
            product=item.product,
            warehouse=warehouse,
            quantity=item.quantity,
            transaction_type=StockTransaction.Type.RELEASE,
            reference=order.order_number,
            user=user,
            notes="Released reserved stock on cancel",
        )


def _restock_after_sale(order, warehouse, user):
    if not _has_stock_txn(order, StockTransaction.Type.SALE):
        return
    if StockTransaction.objects.filter(
        reference=order.order_number,
        transaction_type=StockTransaction.Type.CORRECTION,
        notes="Restocked after cancellation",
    ).exists():
        from apps.accounting.services import reverse_sale_event

        reverse_sale_event(order, user, reason="Order cancelled after sale")
        return
    sales = _order_txns(order, StockTransaction.Type.SALE)
    if sales:
        for txn in sales:
            record_stock_transaction(
                product=txn.product,
                warehouse=txn.warehouse,
                quantity=abs(txn.quantity),
                transaction_type=StockTransaction.Type.CORRECTION,
                reference=order.order_number,
                user=user,
                notes="Restocked after cancellation",
                costing_mode="none",
            )
    else:
        for item in _iter_stock_items(order):
            record_stock_transaction(
                product=item.product,
                warehouse=warehouse,
                quantity=item.quantity,
                transaction_type=StockTransaction.Type.CORRECTION,
                reference=order.order_number,
                user=user,
                notes="Restocked after cancellation",
                costing_mode="none",
            )
    from apps.inventory.costing import restore_order_cogs

    restore_order_cogs(order, reference=order.order_number)
    from apps.accounting.services import reverse_sale_event

    reverse_sale_event(order, user, reason="Order cancelled after sale")


def apply_order_inventory(order, previous_status, new_status, user=None):
    warehouse = _order_warehouse(order)
    if new_status in SALE_STATUSES and previous_status == Order.Status.PENDING:
        _post_sale(order, warehouse, user)
    elif new_status == Order.Status.CANCELLED and previous_status in PRE_DELIVERY_STATUSES:
        if previous_status == Order.Status.PENDING:
            _release_reserve(order, warehouse, user)
        else:
            _restock_after_sale(order, warehouse, user)


def issue_invoice(order):
    if order.invoice_number:
        return order
    order.invoice_number = next_document_number(Order, "invoice_number", "INV")
    order.invoiced_at = timezone.now()
    order.save(update_fields=["invoice_number", "invoiced_at", "updated_at"])
    return order


@transaction.atomic
def place_order(
    *,
    request,
    billing_address,
    shipping_address,
    payment_method,
    notes="",
    coupon_code="",
    payment_proof=None,
):
    items = cart_items(request)
    if not items:
        raise OrderError("Your cart is empty.")

    warehouse = get_default_warehouse()
    product_ids = [row["product"].pk for row in items]
    list(Inventory.objects.select_for_update().filter(product_id__in=product_ids))
    planned = []
    warehouse_qty = {}
    warehouse_map = {}
    for row in items:
        product = row["product"]
        qty = row["quantity"]
        on_hand = available_stock(product)
        if qty > on_hand:
            raise OrderError(
                f"Only {on_hand} unit(s) of {product.name} are available."
            )
        try:
            parts = allocate_stock(product, qty)
        except StockError as exc:
            raise OrderError(str(exc)) from exc
        planned.append((product, parts))
        for part_warehouse, part_qty in parts:
            warehouse_map[part_warehouse.pk] = part_warehouse
            warehouse_qty[part_warehouse.pk] = warehouse_qty.get(part_warehouse.pk, 0) + part_qty
    if warehouse_qty:
        warehouse = warehouse_map[max(warehouse_qty, key=warehouse_qty.get)]
    planned_by_product = {product.pk: parts for product, parts in planned}

    code = (coupon_code or applied_coupon_code(request) or "").strip()
    quote = quote_promotions(items, coupon_code=code or None, user=request.user)
    shipping = settings.SHIPPING_FLAT_RATE if items else Decimal("0.00")
    taxable = quote["merchandise_total"]
    tax = money(taxable * settings.TAX_PERCENT / Decimal("100"))
    grand_total = money(taxable + shipping + tax)

    order = Order.objects.create(
        customer=request.user,
        payment_method_code=payment_method.code,
        payment_status=Order.PaymentStatus.PENDING,
        status=Order.Status.PENDING,
        subtotal=quote["subtotal"],
        discount=quote["coupon_discount"],
        catalog_discount=Decimal("0.00"),
        offer_discount=Decimal("0.00"),
        shipping_charge=shipping,
        tax=tax,
        grand_total=grand_total,
        coupon_code=quote["coupon_code"],
        fulfillment_warehouse=warehouse,
        notes=notes,
        **_copy_address("billing", billing_address),
        **_copy_address("shipping", shipping_address),
    )

    catalog_total = Decimal("0.00")
    offer_total = Decimal("0.00")
    for row in quote["items"]:
        product = row["product"]
        qty = row["quantity"]
        product_discount = row["product_discount"]
        if product.discount_percent:
            catalog_discount = money(
                row["list_price"] * product.discount_percent / Decimal("100") * qty
            )
        else:
            catalog_discount = Decimal("0.00")
        if catalog_discount > product_discount:
            catalog_discount = product_discount
        offer_discount = money(product_discount - catalog_discount)
        catalog_total += catalog_discount
        offer_total += offer_discount
        OrderItem.objects.create(
            order=order,
            product=product,
            sku=product.sku,
            product_name=product.name,
            product_size=product.size,
            product_color=product.variant_parent.color if product.variant_parent_id else product.color,
            quantity=qty,
            unit_price=row["list_price"],
            discount=money(row["product_discount"] + row["coupon_discount"]),
            tax=Decimal("0.00"),
            total=row["line_total"],
            promo_percent=row["promo_percent"] or Decimal("0.00"),
            catalog_discount=catalog_discount,
            offer_discount=offer_discount,
            coupon_discount=row["coupon_discount"],
        )
        try:
            parts = planned_by_product.get(product.pk) or allocate_stock(product, qty)
            for part_warehouse, part_qty in parts:
                record_stock_transaction(
                    product=product,
                    warehouse=part_warehouse,
                    quantity=part_qty,
                    transaction_type=StockTransaction.Type.RESERVE,
                    reference=order.order_number,
                    user=request.user,
                    notes="Reserved on order placement",
                )
        except StockError as exc:
            raise OrderError(str(exc)) from exc

    order.catalog_discount = money(catalog_total)
    order.offer_discount = money(offer_total)
    order.save(update_fields=["catalog_discount", "offer_discount", "updated_at"])

    promotion = quote["coupon"]
    if promotion:
        locked = Promotion.objects.select_for_update().get(pk=promotion.pk)
        if locked.usage_limit is not None and locked.used_count >= locked.usage_limit:
            raise OrderError("This coupon has reached its usage limit.")
        per_customer = locked.usage_limit_per_customer
        if per_customer:
            used = PromotionUsage.objects.filter(promotion=locked, customer=request.user).count()
            if used >= per_customer:
                raise OrderError("You have already used this coupon the allowed number of times.")
        PromotionUsage.objects.create(
            promotion=locked, customer=request.user, order=order
        )
        Promotion.objects.filter(pk=locked.pk).update(used_count=F("used_count") + 1)

    create_payment_for_order(
        order,
        payment_method,
        user=request.user,
        proof_image=payment_proof if payment_method.code != PaymentMethod.Code.COD else None,
    )
    add_status_history(order, Order.Status.PENDING, request.user, "Order placed")
    clear_applied_coupon(request)
    clear_cart(request)
    return order


@transaction.atomic
def change_order_status(order, new_status, user=None, note=""):
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if new_status == locked.status:
        order.refresh_from_db()
        return order
    allowed = STATUS_FLOW.get(locked.status, set())
    if new_status not in allowed and not (user and user.is_superuser):
        raise OrderError(f"Cannot change status from {locked.status} to {new_status}.")

    previous_status = locked.status
    apply_order_inventory(locked, previous_status, new_status, user=user)

    locked.status = new_status
    locked.save(update_fields=["status", "updated_at"])
    add_status_history(locked, new_status, user, note)

    if new_status == Order.Status.CANCELLED:
        restore_coupon_usage(locked)

    if new_status == Order.Status.DELIVERED:
        issue_invoice(locked)

    # COD is collected on delivery — mark payment paid automatically.
    if new_status == Order.Status.DELIVERED and locked.payment_method_code == "cod":
        from apps.payments.services import mark_paid

        payment = locked.payments.order_by("-created_at").first()
        if payment and payment.status != payment.Status.PAID:
            mark_paid(payment, transaction_id=payment.transaction_id or f"COD-{locked.order_number}")

    order.refresh_from_db()
    return order
