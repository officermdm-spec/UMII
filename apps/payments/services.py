from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.gateways import get_gateway
from apps.payments.models import Payment, PaymentMethod


class PaymentError(Exception):
    pass


def create_payment_for_order(order, method, user=None, proof_image=None):
    gateway = get_gateway(method.code)
    payment = Payment.objects.create(
        order=order,
        method=method,
        amount=order.grand_total,
        status=Payment.Status.PENDING,
        proof_image=proof_image,
    )
    result = gateway.initiate(payment)
    payment.transaction_id = result.get("transaction_id", payment.transaction_id)
    payment.gateway_response = result
    if method.code == PaymentMethod.Code.COD:
        order.payment_status = Order.PaymentStatus.COD_PENDING
        payment.status = Payment.Status.PENDING
    else:
        # Screenshot payments wait for staff review — never auto-approve.
        payment.status = Payment.Status.PENDING
        order.payment_status = Order.PaymentStatus.PENDING
        payment.gateway_response = {
            **(result or {}),
            "message": "Awaiting staff verification of payment screenshot.",
        }
    payment.save()
    order.save(update_fields=["payment_status", "updated_at"])
    return payment


@transaction.atomic
def mark_paid(payment, transaction_id="", response=None):
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    if payment.status == Payment.Status.PAID and payment.order.payment_status == Order.PaymentStatus.PAID:
        return payment
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    if transaction_id:
        payment.transaction_id = transaction_id
    if response:
        payment.gateway_response = response
    payment.save()
    order = payment.order
    order.payment_status = Order.PaymentStatus.PAID
    order.save(update_fields=["payment_status", "updated_at"])
    from apps.accounting.services import post_payment_event

    post_payment_event(payment, user=None)
    return payment


def mark_failed(payment, response=None):
    payment.status = Payment.Status.FAILED
    if response:
        payment.gateway_response = response
    payment.save()
    order = payment.order
    order.payment_status = Order.PaymentStatus.FAILED
    order.save(update_fields=["payment_status", "updated_at"])
    return payment


def mark_refunded(payment):
    payment.status = Payment.Status.REFUNDED
    payment.save(update_fields=["status"])
    order = payment.order
    order.payment_status = Order.PaymentStatus.REFUNDED
    order.save(update_fields=["payment_status", "updated_at"])
    from apps.accounting.services import post_refund_event

    post_refund_event(payment)
    return payment


def sync_payment_status(payment, new_status, transaction_id=""):
    """Update payment + linked order.payment_status together."""
    if new_status == Payment.Status.PAID:
        return mark_paid(payment, transaction_id=transaction_id)
    if new_status == Payment.Status.FAILED:
        return mark_failed(payment)
    if new_status == Payment.Status.REFUNDED:
        return mark_refunded(payment)
    if new_status in {Payment.Status.PENDING, Payment.Status.PROCESSING}:
        payment.status = new_status
        if transaction_id:
            payment.transaction_id = transaction_id
        payment.paid_at = None
        payment.save()
        order = payment.order
        if order.payment_method_code == PaymentMethod.Code.COD:
            order.payment_status = Order.PaymentStatus.COD_PENDING
        else:
            order.payment_status = Order.PaymentStatus.PENDING
        order.save(update_fields=["payment_status", "updated_at"])
        return payment
    raise PaymentError(f"Unsupported payment status: {new_status}")


def set_order_payment_status(order, new_status, transaction_id=""):
    """Set order.payment_status and keep the latest payment row in sync."""
    payment = order.payments.order_by("-created_at").first()
    status_map = {
        Order.PaymentStatus.PAID: Payment.Status.PAID,
        Order.PaymentStatus.FAILED: Payment.Status.FAILED,
        Order.PaymentStatus.REFUNDED: Payment.Status.REFUNDED,
        Order.PaymentStatus.PENDING: Payment.Status.PENDING,
        Order.PaymentStatus.COD_PENDING: Payment.Status.PENDING,
    }
    payment_status = status_map.get(new_status)
    if payment_status is None:
        raise PaymentError(f"Unsupported order payment status: {new_status}")
    if payment:
        return sync_payment_status(payment, payment_status, transaction_id=transaction_id)
    order.payment_status = new_status
    order.save(update_fields=["payment_status", "updated_at"])
    return None


def sync_order_payment_status(order, payment_status):
    """Keep Order.payment_status and the latest Payment.status aligned."""
    order.payment_status = payment_status
    order.save(update_fields=["payment_status", "updated_at"])
    payment = order.payments.order_by("-created_at").first()
    if not payment:
        return None
    mapping = {
        Order.PaymentStatus.PENDING: Payment.Status.PENDING,
        Order.PaymentStatus.COD_PENDING: Payment.Status.PENDING,
        Order.PaymentStatus.PAID: Payment.Status.PAID,
        Order.PaymentStatus.FAILED: Payment.Status.FAILED,
        Order.PaymentStatus.REFUNDED: Payment.Status.REFUNDED,
    }
    new_status = mapping.get(payment_status)
    if not new_status or payment.status == new_status:
        return payment
    if new_status == Payment.Status.PAID:
        return mark_paid(payment)
    if new_status == Payment.Status.FAILED:
        return mark_failed(payment)
    if new_status == Payment.Status.REFUNDED:
        return mark_refunded(payment)
    payment.status = new_status
    payment.save(update_fields=["status"])
    return payment


def change_payment_status(payment, new_status, transaction_id=""):
    """Staff/admin helper to move a payment to a concrete status."""
    if new_status == payment.status and not transaction_id:
        return payment
    if new_status == Payment.Status.PAID:
        return mark_paid(payment, transaction_id=transaction_id)
    if new_status == Payment.Status.FAILED:
        return mark_failed(payment)
    if new_status == Payment.Status.REFUNDED:
        return mark_refunded(payment)
    if new_status in {Payment.Status.PENDING, Payment.Status.PROCESSING}:
        payment.status = new_status
        if transaction_id:
            payment.transaction_id = transaction_id
        payment.save()
        order = payment.order
        if payment.method.code == PaymentMethod.Code.COD:
            order.payment_status = Order.PaymentStatus.COD_PENDING
        else:
            order.payment_status = Order.PaymentStatus.PENDING
        order.save(update_fields=["payment_status", "updated_at"])
        return payment
    raise PaymentError(f"Unsupported payment status: {new_status}")
