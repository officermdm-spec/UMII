import uuid

from apps.payments.gateways.base import BaseGateway
from apps.payments.models import Payment


class BankTransferGateway(BaseGateway):
    code = "bank_transfer"

    def initiate(self, payment: Payment) -> dict:
        return {
            "status": Payment.Status.PENDING,
            "transaction_id": f"BNK-{uuid.uuid4().hex[:10].upper()}",
            "message": "Upload or share the transfer receipt with support after payment.",
        }
