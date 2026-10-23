import uuid

from apps.payments.gateways.base import BaseGateway
from apps.payments.models import Payment


class CashOnDeliveryGateway(BaseGateway):
    code = "cod"

    def initiate(self, payment: Payment) -> dict:
        return {
            "status": Payment.Status.PENDING,
            "transaction_id": f"COD-{uuid.uuid4().hex[:10].upper()}",
            "message": "Pay in cash when the order is delivered.",
        }
