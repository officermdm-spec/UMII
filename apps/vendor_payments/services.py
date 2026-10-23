from django.db import transaction

from apps.accounting.models import AccountingPosting, VendorPayment
from apps.accounting.services import post_vendor_payment_event, reverse_journal


class VendorPaymentError(Exception):
    pass


@transaction.atomic
def record_vendor_payment(payment, user=None):
    payment.save()
    post_vendor_payment_event(payment, user)
    return payment


@transaction.atomic
def void_vendor_payment(payment, user=None):
    if payment.status == VendorPayment.Status.VOID:
        raise VendorPaymentError("This vendor payment is already void.")
    posting = (
        AccountingPosting.objects.filter(event_key=f"vendor_payment:{payment.pk}")
        .select_related("journal")
        .first()
    )
    if posting and posting.journal:
        reverse_journal(posting.journal, user=user, reason=f"Void vendor payment #{payment.pk}")
    payment.status = VendorPayment.Status.VOID
    payment.save(update_fields=["status"])
    return payment
