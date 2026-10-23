from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.permissions import is_admin_user
from apps.inventory.models import Inventory, InventoryCostLayer, StockTransaction
from apps.inventory.services import record_stock_transaction
from apps.purchases.models import GRN, ProductPurchaseHistory


class GRNError(Exception):
    pass


@transaction.atomic
def approve_grn(grn, user):
    locked = GRN.objects.select_for_update().get(pk=grn.pk)
    if locked.status == GRN.Status.APPROVED:
        raise GRNError("This GRN is already approved.")
    if locked.status == GRN.Status.CANCELLED:
        raise GRNError("A cancelled GRN cannot be approved.")
    if not locked.items.exists():
        raise GRNError("Add at least one item before approving a GRN.")

    from apps.inventory.costing import apply_weighted_average_cost, create_cost_layer

    for item in locked.items.select_related("product"):
        product = item.product
        avg = apply_weighted_average_cost(product, item.quantity, item.purchase_rate)
        item.average_cost_after = avg
        item.save(update_fields=["average_cost_after"])
        record_stock_transaction(
            product=product,
            warehouse=locked.warehouse,
            quantity=item.quantity,
            transaction_type=StockTransaction.Type.GRN,
            reference=locked.grn_number,
            user=user,
            notes=f"Approved GRN {locked.grn_number}",
        )
        ProductPurchaseHistory.objects.create(
            product=product,
            vendor=locked.vendor,
            grn=locked,
            quantity=item.quantity,
            purchase_rate=item.purchase_rate,
        )
        create_cost_layer(
            product=product,
            warehouse=locked.warehouse,
            quantity=item.quantity,
            purchase_rate=item.purchase_rate,
            grn=locked,
            grn_item=item,
            batch_number=item.batch_number,
            expiry_date=item.expiry_date,
            received_at=timezone.now(),
            notes=f"GRN {locked.grn_number}",
        )

    locked.status = GRN.Status.APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    from apps.accounting.services import post_grn_event

    post_grn_event(locked, user)
    grn.refresh_from_db()
    return locked


def _clear_pending_incoming(grn):
    incoming = StockTransaction.objects.filter(
        reference=grn.grn_number, transaction_type=StockTransaction.Type.INCOMING
    )
    if not incoming.exists():
        return
    for item in grn.items.select_related("product"):
        Inventory.objects.filter(product=item.product, warehouse=grn.warehouse).update(
            incoming_stock=F("incoming_stock") - item.quantity
        )
    Inventory.objects.filter(warehouse=grn.warehouse, incoming_stock__lt=0).update(incoming_stock=0)


@transaction.atomic
def cancel_grn(grn, user=None):
    if grn.status == GRN.Status.APPROVED:
        raise GRNError("Approved GRNs cannot be cancelled or deleted.")
    if grn.status == GRN.Status.CANCELLED:
        return grn
    _clear_pending_incoming(grn)
    grn.status = GRN.Status.CANCELLED
    grn.save(update_fields=["status", "updated_at"])
    return grn


@transaction.atomic
def delete_grn(grn):
    if grn.is_locked:
        raise GRNError("Approved GRNs cannot be edited or deleted.")
    _clear_pending_incoming(grn)
    number = grn.grn_number
    grn.delete()
    return number


@transaction.atomic
def unapprove_grn(grn, user):
    if not is_admin_user(user):
        raise PermissionDenied("Only an admin can unapprove a GRN.")
    locked = GRN.objects.select_for_update().get(pk=grn.pk)
    if locked.status != GRN.Status.APPROVED:
        raise GRNError("Only an approved GRN can be unapproved.")

    items = list(locked.items.select_related("product"))
    for item in items:
        layers = list(InventoryCostLayer.objects.filter(grn_item=item))
        if not layers:
            layers = list(InventoryCostLayer.objects.filter(grn=locked, product=item.product))
        for layer in layers:
            if layer.remaining_qty != layer.received_qty:
                raise GRNError(
                    f"Cannot unapprove {locked.grn_number}: stock from {item.product.sku} has already been sold."
                )
        inventory = (
            Inventory.objects.select_for_update()
            .filter(product=item.product, warehouse=locked.warehouse)
            .first()
        )
        if inventory is None or inventory.current_stock < item.quantity:
            raise GRNError(
                f"Cannot unapprove {locked.grn_number}: not enough on-hand stock for {item.product.sku}."
            )
        if inventory.available_stock < item.quantity:
            raise GRNError(
                f"Cannot unapprove {locked.grn_number}: {item.product.sku} has reserved stock."
            )

    from apps.inventory.costing import remove_weighted_average_cost

    for item in items:
        remove_weighted_average_cost(item.product, item.quantity, item.purchase_rate)
        record_stock_transaction(
            product=item.product,
            warehouse=locked.warehouse,
            quantity=-item.quantity,
            transaction_type=StockTransaction.Type.CORRECTION,
            reference=locked.grn_number,
            user=user,
            notes=f"Unapproved GRN {locked.grn_number}",
            costing_mode="none",
        )
        InventoryCostLayer.objects.filter(grn_item=item).delete()
        item.average_cost_after = 0
        item.save(update_fields=["average_cost_after"])

    ProductPurchaseHistory.objects.filter(grn=locked).delete()

    from apps.accounting.services import reverse_grn_event

    reverse_grn_event(locked, user)

    locked.status = GRN.Status.PENDING
    locked.approved_by = None
    locked.approved_at = None
    locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    grn.refresh_from_db()
    return locked
