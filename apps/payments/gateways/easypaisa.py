import os
import uuid

from apps.payments.gateways.base import BaseGateway
from apps.payments.models import Payment


class EasypaisaGateway(BaseGateway):
    code = "easypaisa"

    def initiate(self, payment: Payment) -> dict:
        store_id = os.getenv("EASYPAISA_STORE_ID", "")
        return {
            "status": Payment.Status.PROCESSING,
            "transaction_id": f"EP-{uuid.uuid4().hex[:10].upper()}",
            "sandbox": not bool(store_id),
            "message": "Complete payment in the Easypaisa app. Store credentials stay in env vars.",
        }
