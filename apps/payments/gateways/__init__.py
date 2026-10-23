from apps.payments.gateways.bank import BankTransferGateway
from apps.payments.gateways.base import BaseGateway
from apps.payments.gateways.cod import CashOnDeliveryGateway
from apps.payments.gateways.easypaisa import EasypaisaGateway
from apps.payments.gateways.jazzcash import JazzCashGateway
from apps.payments.gateways.online import OnlinePaymentGateway


GATEWAY_MAP = {
    "cod": CashOnDeliveryGateway,
    "online": OnlinePaymentGateway,
    "bank_transfer": BankTransferGateway,
    "easypaisa": EasypaisaGateway,
    "jazzcash": JazzCashGateway,
}


def get_gateway(code):
    cls = GATEWAY_MAP.get(code, BaseGateway)
    return cls()
