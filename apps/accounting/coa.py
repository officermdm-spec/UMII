"""Chart of accounts codes used by automated posting."""

from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal("0.00")


def money(value):
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AccountType:
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    CONTRA_REVENUE = "contra_revenue"
    EXPENSE = "expense"


CASH = "1000"
BANK = "1010"
WALLET = "1020"
AR = "1100"
INVENTORY = "1200"
AP = "2000"
REFUND_PAYABLE = "2100"
TAX_PAYABLE = "2200"
CAPITAL = "3000"
RETAINED = "3100"
SALES = "4000"
SHIPPING = "4010"
DISC_PRODUCT = "4100"
DISC_OFFER = "4110"
DISC_ORDER_DISCOUNT = "4120"
SALES_RETURNS = "4130"
COGS = "5000"
EXP_DELIVERY = "5100"
EXP_MARKETING = "5110"
EXP_SALARIES = "5120"
EXP_RENT = "5130"
EXP_ELECTRICITY = "5140"
EXP_INTERNET = "5150"
EXP_PACKAGING = "5160"
EXP_MAINTENANCE = "5170"
EXP_OFFICE = "5180"
EXP_OTHER = "5190"

DEFAULT_ACCOUNTS = [
    (CASH, "Cash", AccountType.ASSET),
    (BANK, "Bank", AccountType.ASSET),
    (WALLET, "Digital Wallet", AccountType.ASSET),
    (AR, "Accounts Receivable", AccountType.ASSET),
    (INVENTORY, "Inventory", AccountType.ASSET),
    (AP, "Accounts Payable", AccountType.LIABILITY),
    (REFUND_PAYABLE, "Customer Refund Payable", AccountType.LIABILITY),
    (TAX_PAYABLE, "Tax Payable", AccountType.LIABILITY),
    (CAPITAL, "Owner Capital", AccountType.EQUITY),
    (RETAINED, "Retained Earnings", AccountType.EQUITY),
    (SALES, "Sales Revenue", AccountType.REVENUE),
    (SHIPPING, "Shipping Revenue", AccountType.REVENUE),
    (DISC_PRODUCT, "Product Discounts", AccountType.CONTRA_REVENUE),
    (DISC_OFFER, "Product Offer Discounts", AccountType.CONTRA_REVENUE),
    (DISC_ORDER_DISCOUNT, "Historical Order Discounts", AccountType.CONTRA_REVENUE),
    (SALES_RETURNS, "Sales Returns", AccountType.CONTRA_REVENUE),
    (COGS, "Cost of Goods Sold", AccountType.EXPENSE),
    (EXP_DELIVERY, "Delivery", AccountType.EXPENSE),
    (EXP_MARKETING, "Marketing", AccountType.EXPENSE),
    (EXP_SALARIES, "Salaries", AccountType.EXPENSE),
    (EXP_RENT, "Rent", AccountType.EXPENSE),
    (EXP_ELECTRICITY, "Electricity", AccountType.EXPENSE),
    (EXP_INTERNET, "Internet", AccountType.EXPENSE),
    (EXP_PACKAGING, "Packaging", AccountType.EXPENSE),
    (EXP_MAINTENANCE, "Maintenance", AccountType.EXPENSE),
    (EXP_OFFICE, "Office", AccountType.EXPENSE),
    (EXP_OTHER, "Other Expenses", AccountType.EXPENSE),
]

PAYMENT_ACCOUNT_MAP = {
    "cod": CASH,
    "bank_transfer": BANK,
    "easypaisa": WALLET,
    "jazzcash": WALLET,
    "online": WALLET,
}

EXPENSE_ACCOUNT_MAP = {
    "delivery": EXP_DELIVERY,
    "marketing": EXP_MARKETING,
    "salaries": EXP_SALARIES,
    "rent": EXP_RENT,
    "electricity": EXP_ELECTRICITY,
    "internet": EXP_INTERNET,
    "packaging": EXP_PACKAGING,
    "maintenance": EXP_MAINTENANCE,
    "office": EXP_OFFICE,
    "other": EXP_OTHER,
}

NORMAL_DEBIT = {AccountType.ASSET, AccountType.EXPENSE, AccountType.CONTRA_REVENUE}
