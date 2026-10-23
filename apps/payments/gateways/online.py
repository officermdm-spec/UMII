import os
import uuid

from apps.payments.gateways.base import BaseGateway
from apps.payments.models import Payment


class OnlinePaymentGateway(BaseGateway):
    """
    Placeholder for a card/online gateway.
    Configure ONLINE_GATEWAY_KEY in the environment before going live.
    """

    code = "online"

    def initiate(self, payment: Payment) -> dict:
        api_key = os.getenv("ONLINE_GATEWAY_KEY", "")
        return {
            "status": Payment.Status.PROCESSING,
            "transaction_id": f"ONL-{uuid.uuid4().hex[:10].upper()}",
            "sandbox": not bool(api_key),
            "message": "Redirect the customer to the hosted checkout page in production.",
        }
