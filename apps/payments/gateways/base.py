import uuid

from apps.payments.models import Payment


class BaseGateway:
    """
    All payment providers implement this interface.
    Credentials belong in environment variables, never in order views.
    """

    code = "base"

    def initiate(self, payment: Payment) -> dict:
        return {
            "status": Payment.Status.PENDING,
            "transaction_id": payment.transaction_id or f"{self.code}-{uuid.uuid4().hex[:12]}",
            "message": "Payment initiated.",
        }

    def verify(self, payment: Payment, payload: dict) -> dict:
        return {"status": payment.status, "payload": payload}
