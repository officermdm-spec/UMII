import os
import uuid

from apps.payments.gateways.base import BaseGateway
from apps.payments.models import Payment


class JazzCashGateway(BaseGateway):
    code = "jazzcash"

    def initiate(self, payment: Payment) -> dict:
        merchant_id = os.getenv("JAZZCASH_MERCHANT_ID", "")
        return {
            "status": Payment.Status.PROCESSING,
            "transaction_id": f"JC-{uuid.uuid4().hex[:10].upper()}",
            "sandbox": not bool(merchant_id),
            "message": "Complete payment in JazzCash. Merchant credentials stay in env vars.",
        }
