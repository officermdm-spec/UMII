from django.db import transaction

from apps.inventory.models import StockTransaction
from apps.inventory.services import (
    allocations_from_order_sales,
    record_stock_transaction,
)
from apps.orders.models import Order
from apps.orders.services import change_order_status
from apps.payments.models import Payment
from apps.payments.services import mark_refunded
from apps.returns.models import ReturnItem, ReturnRequest


class ReturnError(Exception):
    pass


@transaction.atomic
def update_return_status(return_request, new_status, user=None, staff_notes=""):
    previous = return_request.status
    return_request.status = new_status
    if staff_notes:
        return_request.staff_notes = staff_notes
    return_request.save()

    if new_status == ReturnRequest.Status.APPROVED:
        change_order_status(
            return_request.order,
            Order.Status.RETURN_REQUESTED,
            user=user,
            note="Return approved",
        )
    restock_statuses = {
        ReturnRequest.Status.RECEIVED,
        ReturnRequest.Status.INSPECTED,
        ReturnRequest.Status.COMPLETED,
    }
    accounting_statuses = {
        ReturnRequest.Status.RECEIVED,
        ReturnRequest.Status.INSPECTED,
        ReturnRequest.Status.REFUND_PENDING,
        ReturnRequest.Status.REFUNDED,
        ReturnRequest.Status.COMPLETED,
    }
    if new_status in restock_statuses:
        _restock_if_needed(return_request, user)
    if new_status == ReturnRequest.Status.REFUNDED:
        payment = return_request.order.payments.order_by("-created_at").first()
        if payment and payment.status == Payment.Status.PAID:
            mark_refunded(payment)
    if new_status == ReturnRequest.Status.COMPLETED:
        change_order_status(
            return_request.order,
            Order.Status.RETURNED,
            user=user,
            note="Return completed",
        )
    if new_status in accounting_statuses:
        from apps.accounting.services import post_return_event

        post_return_event(return_request, user)
    return return_request


def _restock_if_needed(return_request, user):
    from apps.inventory.costing import restore_order_item_layers

    already = StockTransaction.objects.filter(
        reference=return_request.return_number,
        transaction_type__in=[
            StockTransaction.Type.CUSTOMER_RETURN,
            StockTransaction.Type.DAMAGE,
        ],
    ).exists()
    if already:
        return
    for item in return_request.items.select_related("product", "order_item"):
        if not item.product_id:
            continue
        parts = allocations_from_order_sales(
            return_request.order, item.product, item.quantity
        )
        if item.condition == ReturnItem.Condition.RESELLABLE:
            for part_warehouse, part_qty in parts:
                record_stock_transaction(
                    product=item.product,
                    warehouse=part_warehouse,
                    quantity=part_qty,
                    transaction_type=StockTransaction.Type.CUSTOMER_RETURN,
                    reference=return_request.return_number,
                    user=user,
                    notes="Resellable customer return",
                    costing_mode="none",
                )
            restore_order_item_layers(
                item.order_item,
                item.quantity,
                return_item=item,
                reference=return_request.return_number,
            )
        elif item.condition == ReturnItem.Condition.DAMAGED:
            for part_warehouse, part_qty in parts:
                record_stock_transaction(
                    product=item.product,
                    warehouse=part_warehouse,
                    quantity=part_qty,
                    transaction_type=StockTransaction.Type.CUSTOMER_RETURN,
                    reference=return_request.return_number,
                    user=user,
                    notes="Damaged unit received then marked damage",
                    costing_mode="none",
                )
                record_stock_transaction(
                    product=item.product,
                    warehouse=part_warehouse,
                    quantity=-part_qty,
                    transaction_type=StockTransaction.Type.DAMAGE,
                    reference=return_request.return_number,
                    user=user,
                    notes="Removed damaged return from sellable stock",
                    costing_mode="none",
                )
