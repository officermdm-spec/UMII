from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounting.coa import (
    AP,
    AR,
    BANK,
    CASH,
    COGS,
    DISC_COUPON,
    DISC_OFFER,
    DISC_PRODUCT,
    EXPENSE_ACCOUNT_MAP,
    INVENTORY,
    OTHER_INCOME,
    PAYMENT_ACCOUNT_MAP,
    REFUND_PAYABLE,
    SALES,
    SALES_RETURNS,
    SHIPPING,
    TAX_PAYABLE,
    WALLET,
    money,
    ZERO,
)
from apps.accounting.models import Account, AccountingPosting, AuditLog, JournalEntry, JournalLine
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.returns.models import ReturnItem


class AccountingError(Exception):
    pass


def ensure_accounts():
    from apps.accounting.coa import DEFAULT_ACCOUNTS

    for code, name, account_type in DEFAULT_ACCOUNTS:
        Account.objects.get_or_create(
            code=code, defaults={"name": name, "account_type": account_type}
        )


def get_account(code):
    ensure_accounts()
    try:
        return Account.objects.get(code=code, is_active=True)
    except Account.DoesNotExist as exc:
        raise AccountingError(f"Account {code} is missing.") from exc


def cash_account_code(method_code=None, payment_account=None):
    if payment_account:
        mapping = {"cash": CASH, "bank": BANK, "wallet": WALLET}
        return mapping.get(payment_account, CASH)
    return PAYMENT_ACCOUNT_MAP.get(method_code or "", CASH)


def record_audit(user, action, *, reference_type="", reference_id="", amount=ZERO, notes=""):
    AuditLog.objects.create(
        user=user,
        action=action,
        reference_type=reference_type,
        reference_id=str(reference_id or ""),
        amount=money(amount),
        notes=notes,
    )


def _clean_lines(raw_lines):
    lines = []
    for row in raw_lines:
        debit = money(row.get("debit") or ZERO)
        credit = money(row.get("credit") or ZERO)
        if debit < ZERO or credit < ZERO:
            raise AccountingError("Amounts cannot be negative.")
        if debit and credit:
            raise AccountingError("A journal line cannot be both debit and credit.")
        if debit == ZERO and credit == ZERO:
            continue
        lines.append(
            {
                "account": get_account(row["account"]),
                "debit": debit,
                "credit": credit,
                "memo": row.get("memo") or "",
            }
        )
    return lines


@transaction.atomic
def post_journal(*, reference_type, reference_id, description, lines, user=None, entry_at=None, event_key=None):
    ensure_accounts()
    key = event_key or f"{reference_type}:{reference_id}"
    existing = AccountingPosting.objects.filter(event_key=key).select_related("journal").first()
    if existing:
        return existing.journal
    cleaned = _clean_lines(lines)
    debit_total = sum((row["debit"] for row in cleaned), ZERO)
    credit_total = sum((row["credit"] for row in cleaned), ZERO)
    if debit_total != credit_total:
        raise AccountingError(f"Journal is not balanced: debit {debit_total} credit {credit_total}.")
    if debit_total == ZERO:
        return None
    journal = JournalEntry.objects.create(
        entry_at=entry_at or timezone.now(),
        reference_type=reference_type,
        reference_id=str(reference_id),
        description=description,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    for row in cleaned:
        JournalLine.objects.create(
            journal=journal,
            account=row["account"],
            debit=row["debit"],
            credit=row["credit"],
            memo=row["memo"],
        )
    try:
        AccountingPosting.objects.create(event_key=key, journal=journal)
    except IntegrityError:
        journal.delete()
        return AccountingPosting.objects.get(event_key=key).journal
    record_audit(
        user,
        "journal_posted",
        reference_type=reference_type,
        reference_id=reference_id,
        amount=debit_total,
        notes=description,
    )
    return journal


def reverse_journal(journal, user=None, reason=""):
    if not journal or journal.status == JournalEntry.Status.REVERSED:
        return journal
    key = f"reversal:{journal.number}"
    if AccountingPosting.objects.filter(event_key=key).exists():
        journal.status = JournalEntry.Status.REVERSED
        journal.save(update_fields=["status"])
        return journal
    lines = [
        {
            "account": line.account.code,
            "debit": line.credit,
            "credit": line.debit,
            "memo": f"Reversal of {journal.number}",
        }
        for line in journal.lines.all()
    ]
    reversal = post_journal(
        reference_type=journal.reference_type,
        reference_id=journal.reference_id,
        description=reason or f"Reversal of {journal.number}",
        lines=lines,
        user=user,
        event_key=key,
    )
    journal.status = JournalEntry.Status.REVERSED
    journal.reversed_by = reversal
    journal.save(update_fields=["status", "reversed_by"])
    return reversal


def _posting_journal(event_key):
    row = AccountingPosting.objects.filter(event_key=event_key).select_related("journal").first()
    return row.journal if row else None


def post_grn_event(grn, user=None):
    amount = money(grn.grand_total)
    return post_journal(
        reference_type="grn",
        reference_id=grn.pk,
        description=f"GRN {grn.grn_number} approved",
        lines=[
            {"account": INVENTORY, "debit": amount, "credit": ZERO},
            {"account": AP, "debit": ZERO, "credit": amount},
        ],
        user=user,
        event_key=f"grn_approved:{grn.pk}",
    )


def reverse_event(event_key, user=None, reason=""):
    journal = _posting_journal(event_key)
    if not journal:
        return None
    return reverse_journal(journal, user=user, reason=reason)


def reverse_grn_event(grn, user=None):
    return reverse_event(f"grn_approved:{grn.pk}", user=user, reason=f"Unapprove GRN {grn.grn_number}")


def post_sale_event(order, user=None):
    order.refresh_from_db()
    gross = money(sum((item.unit_price * item.quantity for item in order.items.all()), ZERO))
    catalog = money(order.catalog_discount)
    offer = money(order.offer_discount)
    coupon = money(order.discount)
    shipping = money(order.shipping_charge)
    tax = money(order.tax)
    cogs = money(order.cogs_total)
    ar = money(order.grand_total)
    lines = [
        {"account": AR, "debit": ar, "credit": ZERO, "memo": order.order_number},
        {"account": DISC_PRODUCT, "debit": catalog, "credit": ZERO},
        {"account": DISC_OFFER, "debit": offer, "credit": ZERO},
        {"account": DISC_COUPON, "debit": coupon, "credit": ZERO},
        {"account": SALES, "debit": ZERO, "credit": gross},
        {"account": SHIPPING, "debit": ZERO, "credit": shipping},
        {"account": TAX_PAYABLE, "debit": ZERO, "credit": tax},
        {"account": COGS, "debit": cogs, "credit": ZERO},
        {"account": INVENTORY, "debit": ZERO, "credit": cogs},
    ]
    return post_journal(
        reference_type="order",
        reference_id=order.pk,
        description=f"Sale {order.order_number}",
        lines=lines,
        user=user,
        event_key=f"sale:{order.pk}",
    )


def reverse_sale_event(order, user=None, reason=""):
    journal = _posting_journal(f"sale:{order.pk}")
    if not journal:
        return None
    return reverse_journal(journal, user=user, reason=reason or f"Reverse sale {order.order_number}")


def post_payment_event(payment, user=None):
    if payment.status != Payment.Status.PAID:
        return None
    cash_code = cash_account_code(payment.method.code)
    amount = money(payment.amount)
    return post_journal(
        reference_type="payment",
        reference_id=payment.pk,
        description=f"Payment {payment.order.order_number}",
        lines=[
            {"account": cash_code, "debit": amount, "credit": ZERO},
            {"account": AR, "debit": ZERO, "credit": amount},
        ],
        user=user,
        event_key=f"payment_paid:{payment.pk}",
    )


def post_refund_event(payment, user=None):
    cash_code = cash_account_code(payment.method.code)
    amount = money(payment.amount)
    return_posted = AccountingPosting.objects.filter(
        event_key__startswith=f"return_revenue:{payment.order_id}:"
    ).exists()
    source = REFUND_PAYABLE if return_posted else AR
    return post_journal(
        reference_type="refund",
        reference_id=payment.pk,
        description=f"Refund {payment.order.order_number}",
        lines=[
            {"account": source, "debit": amount, "credit": ZERO},
            {"account": cash_code, "debit": ZERO, "credit": amount},
        ],
        user=user,
        event_key=f"payment_refunded:{payment.pk}",
    )


def _line_return_share(item):
    from decimal import Decimal as D

    order_item = item.order_item
    if not order_item.quantity:
        return ZERO, ZERO, ZERO, ZERO, ZERO, ZERO
    ratio = D(item.quantity) / D(order_item.quantity)
    gross = money(order_item.unit_price * item.quantity)
    catalog = money(order_item.catalog_discount * ratio)
    offer = money(order_item.offer_discount * ratio)
    coupon = money(order_item.coupon_discount * ratio)
    net = money(gross - catalog - offer - coupon)
    cogs = (
        money(order_item.cogs_amount * ratio)
        if item.condition == ReturnItem.Condition.RESELLABLE
        else ZERO
    )
    return gross, catalog, offer, coupon, net, cogs


def post_return_event(return_request, user=None):
    gross = catalog = offer = coupon = net = cogs = ZERO
    for item in return_request.items.select_related("order_item"):
        g, cat, off, coup, n, c = _line_return_share(item)
        gross += g
        catalog += cat
        offer += off
        coupon += coup
        net += n
        cogs += c
    order = return_request.order
    paid = order.payment_status == Order.PaymentStatus.PAID
    credit_account = REFUND_PAYABLE if paid else AR
    lines = [
        {"account": SALES_RETURNS, "debit": net, "credit": ZERO},
        {"account": credit_account, "debit": ZERO, "credit": net},
        {"account": INVENTORY, "debit": cogs, "credit": ZERO},
        {"account": COGS, "debit": ZERO, "credit": cogs},
    ]
    post_journal(
        reference_type="return",
        reference_id=return_request.pk,
        description=f"Return {return_request.return_number}",
        lines=lines,
        user=user,
        event_key=f"return_revenue:{order.pk}:{return_request.pk}",
    )


def post_expense_event(expense, user=None):
    cash_code = cash_account_code(payment_account=expense.payment_account)
    exp_code = EXPENSE_ACCOUNT_MAP.get(expense.category, EXPENSE_ACCOUNT_MAP["other"])
    amount = money(expense.amount)
    return post_journal(
        reference_type="expense",
        reference_id=expense.pk,
        description=f"Expense: {expense.get_category_display()}",
        lines=[
            {"account": exp_code, "debit": amount, "credit": ZERO},
            {"account": cash_code, "debit": ZERO, "credit": amount},
        ],
        user=user,
        event_key=f"expense:{expense.pk}",
    )


def post_other_income_event(income, user=None):
    cash_code = cash_account_code(payment_account=income.payment_account)
    amount = money(income.amount)
    return post_journal(
        reference_type="other_income",
        reference_id=income.pk,
        description=income.title,
        lines=[
            {"account": cash_code, "debit": amount, "credit": ZERO},
            {"account": OTHER_INCOME, "debit": ZERO, "credit": amount},
        ],
        user=user,
        event_key=f"other_income:{income.pk}",
    )


def post_vendor_payment_event(payment, user=None):
    cash_code = cash_account_code(payment_account=payment.payment_account)
    amount = money(payment.amount)
    return post_journal(
        reference_type="vendor_payment",
        reference_id=payment.pk,
        description=f"Vendor payment {payment.vendor}",
        lines=[
            {"account": AP, "debit": amount, "credit": ZERO},
            {"account": cash_code, "debit": ZERO, "credit": amount},
        ],
        user=user,
        event_key=f"vendor_payment:{payment.pk}",
    )


def account_movement(code, start=None, end=None):
    qs = JournalLine.objects.filter(account__code=code, journal__status=JournalEntry.Status.POSTED)
    if start:
        qs = qs.filter(journal__entry_at__date__gte=start)
    if end:
        qs = qs.filter(journal__entry_at__date__lte=end)
    row = qs.aggregate(debit=Sum("debit"), credit=Sum("credit"))
    return money(row["debit"] or ZERO), money(row["credit"] or ZERO)


def account_balance(code, start=None, end=None):
    from apps.accounting.coa import NORMAL_DEBIT
    from apps.accounting.models import Account

    debit, credit = account_movement(code, start, end)
    account = Account.objects.filter(code=code).first()
    if account and account.account_type in NORMAL_DEBIT:
        return money(debit - credit)
    return money(credit - debit)


def period_totals(start, end):
    def net(code):
        d, c = account_movement(code, start, end)
        return money(d - c)

    def credit_net(code):
        d, c = account_movement(code, start, end)
        return money(c - d)

    gross_sales = credit_net(SALES)
    product_discounts = net(DISC_PRODUCT)
    offer_discounts = net(DISC_OFFER)
    coupon_discounts = net(DISC_COUPON)
    sales_returns = net(SALES_RETURNS)
    shipping = credit_net(SHIPPING)
    other_income = credit_net(OTHER_INCOME)
    cogs = net(COGS)
    net_sales = money(gross_sales - product_discounts - offer_discounts - coupon_discounts - sales_returns)
    gross_profit = money(net_sales - cogs)
    expense_codes = [
        "5100",
        "5110",
        "5120",
        "5130",
        "5140",
        "5150",
        "5160",
        "5170",
        "5180",
        "5190",
    ]
    expenses = sum((net(code) for code in expense_codes), ZERO)
    net_profit = money(gross_profit + other_income - expenses)
    return {
        "gross_sales": gross_sales,
        "product_discounts": product_discounts,
        "offer_discounts": offer_discounts,
        "coupon_discounts": coupon_discounts,
        "sales_returns": sales_returns,
        "net_sales": net_sales,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "shipping": shipping,
        "other_income": other_income,
        "expenses": money(expenses),
        "net_profit": net_profit,
        "cash": account_balance(CASH),
        "bank": account_balance(BANK),
        "wallet": account_balance(WALLET),
        "receivables": account_balance(AR),
        "payables": account_balance(AP),
        "inventory_account": account_balance(INVENTORY),
    }
