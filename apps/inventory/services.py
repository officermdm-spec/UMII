from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Sum

from apps.inventory.models import Inventory, StockTransaction, Warehouse
from apps.products.models import Product


class StockError(Exception):
    pass


def get_default_warehouse():
    warehouse = Warehouse.objects.filter(is_active=True).order_by("id").first()
    if warehouse is None:
        warehouse = Warehouse.objects.create(
            name="Main Warehouse",
            code="MAIN",
            address="Head office",
        )
    return warehouse


def ensure_inventory(product, warehouse=None):
    """Guarantee an inventory row exists for product @ warehouse."""
    warehouse = warehouse or get_default_warehouse()
    inventory, _ = Inventory.objects.get_or_create(
        product=product,
        warehouse=warehouse,
        defaults={
            "current_stock": 0,
            "reserved_stock": 0,
            "incoming_stock": 0,
            "sold_quantity": 0,
            "returned_quantity": 0,
            "damaged_quantity": 0,
        },
    )
    return inventory


def _sync_product_stock(product):
    total = (
        Inventory.objects.filter(product=product).aggregate(total=Sum("current_stock"))["total"]
        or 0
    )
    Product.objects.filter(pk=product.pk).update(stock_quantity=total)
    product.stock_quantity = total
    return total


@transaction.atomic
def record_stock_transaction(
    *,
    product,
    warehouse,
    quantity,
    transaction_type,
    reference,
    user=None,
    notes="",
    costing_mode=None,
):
    """
    Every stock change MUST go through this function.
    `quantity` is signed: positive increases on-hand stock, negative decreases it.
    """
    if quantity == 0:
        raise StockError("Quantity cannot be zero.")

    inventory, _ = Inventory.objects.select_for_update().get_or_create(
        product=product,
        warehouse=warehouse,
        defaults={
            "current_stock": 0,
            "reserved_stock": 0,
            "incoming_stock": 0,
            "sold_quantity": 0,
            "returned_quantity": 0,
            "damaged_quantity": 0,
        },
    )

    txn_type = transaction_type
    if txn_type == StockTransaction.Type.GRN:
        if quantity < 0:
            raise StockError("GRN quantity must be positive.")
        inventory.current_stock = F("current_stock") + quantity
        inventory.incoming_stock = F("incoming_stock") - quantity
    elif txn_type == StockTransaction.Type.INCOMING:
        if quantity < 0:
            raise StockError("Incoming quantity must be positive.")
        inventory.incoming_stock = F("incoming_stock") + quantity
    elif txn_type == StockTransaction.Type.SALE:
        if quantity >= 0:
            raise StockError("Sale quantity must be negative.")
        inventory.current_stock = F("current_stock") + quantity
        inventory.sold_quantity = F("sold_quantity") + abs(quantity)
        inventory.reserved_stock = F("reserved_stock") - abs(quantity)
    elif txn_type == StockTransaction.Type.RESERVE:
        if quantity <= 0:
            raise StockError("Reserve quantity must be positive.")
        available = inventory.available_stock
        if available < quantity:
            raise StockError(
                f"Insufficient stock for {product.sku}. Available: {available}, requested: {quantity}."
            )
        inventory.reserved_stock = F("reserved_stock") + quantity
    elif txn_type == StockTransaction.Type.RELEASE:
        inventory.reserved_stock = F("reserved_stock") - abs(quantity)
    elif txn_type == StockTransaction.Type.CUSTOMER_RETURN:
        if quantity <= 0:
            raise StockError("Return quantity must be positive.")
        inventory.current_stock = F("current_stock") + quantity
        inventory.returned_quantity = F("returned_quantity") + abs(quantity)
    elif txn_type == StockTransaction.Type.DAMAGE:
        if quantity >= 0:
            raise StockError("Damage quantity must be negative (stock removed).")
        inventory.current_stock = F("current_stock") + quantity
        inventory.damaged_quantity = F("damaged_quantity") + abs(quantity)
    elif txn_type in {StockTransaction.Type.ADJUSTMENT, StockTransaction.Type.CORRECTION}:
        inventory.current_stock = F("current_stock") + quantity
    else:
        raise StockError(f"Unknown transaction type: {txn_type}")

    inventory.save()
    inventory.refresh_from_db()
    if inventory.current_stock < 0:
        raise StockError(f"Stock for {product.sku} cannot go negative.")
    if inventory.reserved_stock < 0:
        inventory.reserved_stock = 0
        inventory.save(update_fields=["reserved_stock"])
    if inventory.incoming_stock < 0:
        inventory.incoming_stock = 0
        inventory.save(update_fields=["incoming_stock"])
    if inventory.reserved_stock > inventory.current_stock:
        inventory.reserved_stock = inventory.current_stock
        inventory.save(update_fields=["reserved_stock"])

    StockTransaction.objects.create(
        product=product,
        warehouse=warehouse,
        quantity=quantity,
        transaction_type=txn_type,
        reference=reference,
        user=user,
        notes=notes,
    )
    _sync_product_stock(product)
    if costing_mode is None:
        costing_mode = (
            "auto"
            if txn_type
            in {
                StockTransaction.Type.ADJUSTMENT,
                StockTransaction.Type.CORRECTION,
                StockTransaction.Type.DAMAGE,
            }
            else "none"
        )
    if costing_mode == "auto":
        from apps.inventory.costing import apply_adjustment_costing

        apply_adjustment_costing(product, warehouse, quantity, txn_type, reference)
    return inventory


def available_stock(product, warehouse=None):
    qs = Inventory.objects.filter(product=product)
    if warehouse:
        qs = qs.filter(warehouse=warehouse)
    row = qs.aggregate(
        current=Sum("current_stock"),
        reserved=Sum("reserved_stock"),
    )
    return (row["current"] or 0) - (row["reserved"] or 0)


def visible_inventory_q():
    """Hide empty ghost rows (e.g. unused Main Warehouse) that never had a transaction."""
    has_txn = StockTransaction.objects.filter(
        product_id=OuterRef("product_id"),
        warehouse_id=OuterRef("warehouse_id"),
    )
    return (
        Q(current_stock__gt=0)
        | Q(reserved_stock__gt=0)
        | Q(incoming_stock__gt=0)
        | Q(sold_quantity__gt=0)
        | Q(returned_quantity__gt=0)
        | Q(damaged_quantity__gt=0)
        | Exists(has_txn)
    )


def allocate_stock(product, quantity):
    """
    Split a quantity across warehouses that actually have available stock.
    Prefers a single warehouse that can fulfill the whole line.
    """
    needed = int(quantity)
    if needed <= 0:
        raise StockError("Quantity must be positive.")
    rows = list(
        Inventory.objects.filter(product=product)
        .select_related("warehouse")
        .order_by("-current_stock", "warehouse_id")
    )
    available_rows = [
        (inv.warehouse, inv.available_stock) for inv in rows if inv.available_stock > 0
    ]
    total = sum(qty for _, qty in available_rows)
    if needed > total:
        raise StockError(
            f"Insufficient stock for {product.sku}. Available: {total}, requested: {needed}."
        )
    for warehouse, on_hand in available_rows:
        if on_hand >= needed:
            return [(warehouse, needed)]
    remaining = needed
    allocation = []
    for warehouse, on_hand in available_rows:
        if remaining <= 0:
            break
        take = min(on_hand, remaining)
        if take:
            allocation.append((warehouse, take))
            remaining -= take
    return allocation


def allocations_from_order_sales(order, product, quantity):
    """Put returned qty back into the warehouses that originally sold it."""
    needed = int(quantity)
    sales = list(
        StockTransaction.objects.filter(
            reference=order.order_number,
            product=product,
            transaction_type=StockTransaction.Type.SALE,
        ).select_related("warehouse")
    )
    if not sales:
        warehouse = order.fulfillment_warehouse or get_default_warehouse()
        return [(warehouse, needed)]
    remaining = needed
    out = []
    for txn in sales:
        if remaining <= 0:
            break
        take = min(abs(txn.quantity), remaining)
        if take:
            out.append((txn.warehouse, take))
            remaining -= take
    if remaining > 0:
        warehouse = sales[-1].warehouse
        if out and out[-1][0].pk == warehouse.pk:
            out[-1] = (warehouse, out[-1][1] + remaining)
        else:
            out.append((warehouse, remaining))
    return out


def inventory_health(inventory):
    """Return a simple status label for staff UI."""
    available = inventory.available_stock
    min_level = inventory.product.min_stock_level
    if available <= 0:
        return "out"
    if available <= min_level:
        return "low"
    return "ok"
