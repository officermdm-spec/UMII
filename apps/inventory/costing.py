"""FIFO inventory costing per product + warehouse."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.inventory.models import CostLayerConsumption, Inventory, InventoryCostLayer
from apps.inventory.services import StockError

ZERO = Decimal("0.00")


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def on_hand_qty(product):
    return int(
        Inventory.objects.filter(product=product).aggregate(s=Sum("current_stock"))["s"] or 0
    )


def apply_weighted_average_cost(product, quantity, purchase_rate):
    """
    New Average Cost = [(Existing Total Stock * Old Cost) + (New Qty * New Rate)]
                       / (Existing Total Stock + New Qty)
    Call this BEFORE adding the new GRN quantity to inventory.
    """
    from apps.products.models import Product

    qty = int(quantity)
    rate = money(purchase_rate)
    existing = on_hand_qty(product)
    old = money(product.purchase_price)
    denom = existing + qty
    if denom <= 0:
        return old
    avg = money((existing * old + qty * rate) / denom)
    Product.objects.filter(pk=product.pk).update(purchase_price=avg)
    product.purchase_price = avg
    return avg


def remove_weighted_average_cost(product, quantity, purchase_rate):
    """Reverse a WAC add. Call while the GRN quantity is still on hand."""
    from apps.products.models import Product

    qty = int(quantity)
    rate = money(purchase_rate)
    existing = on_hand_qty(product)
    old = money(product.purchase_price)
    remain = existing - qty
    if remain <= 0:
        return old
    avg = money((existing * old - qty * rate) / remain)
    if avg < ZERO:
        avg = ZERO
    Product.objects.filter(pk=product.pk).update(purchase_price=avg)
    product.purchase_price = avg
    return avg


def wac_inventory_value(product=None):
    qs = Inventory.objects.select_related("product")
    if product is not None:
        qs = qs.filter(product=product)
    total = ZERO
    for inv in qs:
        if inv.current_stock:
            total += money(inv.current_stock * inv.product.purchase_price)
    return total


def create_cost_layer(
    *,
    product,
    warehouse,
    quantity,
    purchase_rate,
    grn=None,
    grn_item=None,
    batch_number="",
    expiry_date=None,
    received_at=None,
    notes="",
):
    qty = int(quantity)
    if qty <= 0:
        raise StockError("Cost layer quantity must be positive.")
    return InventoryCostLayer.objects.create(
        product=product,
        warehouse=warehouse,
        grn=grn,
        grn_item=grn_item,
        purchase_rate=money(purchase_rate),
        received_qty=qty,
        remaining_qty=qty,
        batch_number=batch_number or "",
        expiry_date=expiry_date,
        received_at=received_at or timezone.now(),
        notes=notes,
    )


@transaction.atomic
def consume_fifo(
    product,
    warehouse,
    quantity,
    *,
    order_item=None,
    return_item=None,
    kind=CostLayerConsumption.Kind.SALE,
    reference="",
):
    needed = int(quantity)
    if needed <= 0:
        return []
    uses = []
    layers = (
        InventoryCostLayer.objects.select_for_update()
        .filter(product=product, warehouse=warehouse, remaining_qty__gt=0)
        .order_by("received_at", "id")
    )
    remaining = needed
    for layer in layers:
        if remaining <= 0:
            break
        take = min(layer.remaining_qty, remaining)
        layer.remaining_qty = F("remaining_qty") - take
        layer.save(update_fields=["remaining_qty"])
        layer.refresh_from_db()
        if layer.remaining_qty < 0:
            raise StockError("Cost layer remaining quantity cannot be negative.")
        amount = money(layer.purchase_rate * take)
        uses.append(
            CostLayerConsumption.objects.create(
                layer=layer,
                order_item=order_item,
                return_item=return_item,
                quantity=take,
                unit_cost=layer.purchase_rate,
                amount=amount,
                kind=kind,
                reference=reference,
            )
        )
        remaining -= take
    if remaining > 0:
        raise StockError(
            f"Insufficient costed stock for {product.sku} at {warehouse.code}. "
            f"Needed {needed}, short {remaining}."
        )
    return uses


def restore_fifo_uses(uses, *, return_item=None, reference=""):
    restored = []
    for use in reversed(list(uses)):
        layer = InventoryCostLayer.objects.select_for_update().get(pk=use.layer_id)
        layer.remaining_qty = F("remaining_qty") + use.quantity
        layer.save(update_fields=["remaining_qty"])
        restored.append(
            CostLayerConsumption.objects.create(
                layer=layer,
                order_item=use.order_item,
                return_item=return_item,
                quantity=use.quantity,
                unit_cost=use.unit_cost,
                amount=use.amount,
                kind=CostLayerConsumption.Kind.RESTORE,
                reference=reference,
            )
        )
    return restored


def restore_order_item_layers(order_item, quantity, *, return_item=None, reference=""):
    qty = int(quantity)
    if qty <= 0:
        return ZERO, []
    sold = list(
        CostLayerConsumption.objects.select_related("layer")
        .filter(order_item=order_item, kind=CostLayerConsumption.Kind.SALE)
        .order_by("id")
    )
    already = (
        CostLayerConsumption.objects.filter(
            order_item=order_item, kind=CostLayerConsumption.Kind.RESTORE
        ).aggregate(s=Sum("quantity"))["s"]
        or 0
    )
    available = sum(use.quantity for use in sold) - already
    take = min(qty, available)
    if take <= 0:
        return ZERO, []
    remaining = take
    restored_uses = []
    total = ZERO
    for use in reversed(sold):
        if remaining <= 0:
            break
        portion = min(use.quantity, remaining)
        layer = InventoryCostLayer.objects.select_for_update().get(pk=use.layer_id)
        layer.remaining_qty = F("remaining_qty") + portion
        layer.save(update_fields=["remaining_qty"])
        amount = money(use.unit_cost * portion)
        restored_uses.append(
            CostLayerConsumption.objects.create(
                layer=layer,
                order_item=order_item,
                return_item=return_item,
                quantity=portion,
                unit_cost=use.unit_cost,
                amount=amount,
                kind=CostLayerConsumption.Kind.RESTORE,
                reference=reference,
            )
        )
        total += amount
        remaining -= portion
    return total, restored_uses


@transaction.atomic
def consume_order_cogs(order, warehouse=None):
    from apps.inventory.models import StockTransaction
    from apps.inventory.services import get_default_warehouse

    total = ZERO
    items = {
        item.product_id: item
        for item in order.items.select_related("product")
        if item.product_id
    }
    reserves = list(
        StockTransaction.objects.filter(
            reference=order.order_number,
            transaction_type=StockTransaction.Type.RESERVE,
        ).select_related("product", "warehouse")
    )
    allocations = defaultdict(list)
    if reserves:
        for txn in reserves:
            allocations[txn.product_id].append((txn.warehouse, txn.quantity, txn.product))
    else:
        fallback = warehouse or get_default_warehouse()
        for item in items.values():
            allocations[item.product_id].append((fallback, item.quantity, item.product))

    for product_id, parts in allocations.items():
        item = items.get(product_id)
        if not item:
            continue
        existing = CostLayerConsumption.objects.filter(
            order_item=item, kind=CostLayerConsumption.Kind.SALE
        ).exists()
        if existing:
            total += item.cogs_amount or ZERO
            continue
        for wh, qty, product in parts:
            consume_fifo(
                product,
                wh,
                qty,
                order_item=item,
                kind=CostLayerConsumption.Kind.SALE,
                reference=order.order_number,
            )
        wac_unit = money(item.product.purchase_price)
        item.unit_cost = wac_unit
        item.cogs_amount = money(wac_unit * item.quantity)
        item.save(update_fields=["unit_cost", "cogs_amount"])
        total += item.cogs_amount
    order.cogs_total = money(total)
    order.save(update_fields=["cogs_total", "updated_at"])
    return order.cogs_total


def restore_order_cogs(order, *, reference=""):
    total = ZERO
    for item in order.items.all():
        amount, _ = restore_order_item_layers(
            item, item.quantity, reference=reference or order.order_number
        )
        total += amount
        item.cogs_amount = ZERO
        item.unit_cost = ZERO
        item.save(update_fields=["cogs_amount", "unit_cost"])
    order.cogs_total = ZERO
    order.save(update_fields=["cogs_total", "updated_at"])
    return total


def layer_value(product=None, warehouse=None):
    qs = InventoryCostLayer.objects.filter(remaining_qty__gt=0)
    if product is not None:
        qs = qs.filter(product=product)
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    total = ZERO
    for layer in qs:
        total += money(layer.purchase_rate * layer.remaining_qty)
    return total


def apply_adjustment_costing(product, warehouse, quantity, transaction_type, reference):
    """Non-GRN stock increases are layered at the current reference purchase price."""
    from apps.inventory.models import StockTransaction

    if transaction_type in {
        StockTransaction.Type.ADJUSTMENT,
        StockTransaction.Type.CORRECTION,
    } and quantity > 0:
        create_cost_layer(
            product=product,
            warehouse=warehouse,
            quantity=quantity,
            purchase_rate=product.purchase_price,
            notes=f"Adjustment {reference}",
        )
    elif transaction_type in {
        StockTransaction.Type.ADJUSTMENT,
        StockTransaction.Type.CORRECTION,
        StockTransaction.Type.DAMAGE,
    } and quantity < 0:
        consume_fifo(
            product,
            warehouse,
            abs(quantity),
            kind=CostLayerConsumption.Kind.WRITE_OFF,
            reference=reference,
        )
