from django.db.models import Count, Sum

from apps.accounting.coa import money, ZERO
from apps.accounting.models import JournalEntry, JournalLine
from apps.accounting.services import account_balance
from apps.inventory.costing import layer_value
from apps.inventory.models import Inventory, InventoryCostLayer
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.products.models import Product
from apps.purchases.models import GRN
from apps.returns.models import ReturnRequest


def run_reconciliation():
    """Detect issues. Never silently repair financial records."""
    issues = []

    for inv in Inventory.objects.select_related("product", "warehouse"):
        layered = (
            InventoryCostLayer.objects.filter(
                product=inv.product, warehouse=inv.warehouse
            ).aggregate(s=Sum("remaining_qty"))["s"]
            or 0
        )
        if layered != inv.current_stock:
            issues.append(
                {
                    "code": "inventory_mismatch",
                    "message": (
                        f"{inv.product.sku} @ {inv.warehouse.code}: stock {inv.current_stock} "
                        f"vs cost layers {layered}"
                    ),
                }
            )

    layer_val = layer_value()
    account_val = account_balance("1200")
    if layer_val != account_val:
        issues.append(
            {
                "code": "inventory_valuation_mismatch",
                "message": f"Cost layers {layer_val} vs inventory account {account_val}",
            }
        )

    sold = Order.objects.filter(
        status__in=[
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.IN_PROGRESS,
            Order.Status.ON_WAY,
            Order.Status.DELIVERED,
            Order.Status.RECEIVED,
        ]
    )
    from apps.accounting.models import AccountingPosting

    for order in sold:
        posts = AccountingPosting.objects.filter(event_key=f"sale:{order.pk}").count()
        if posts == 0:
            issues.append({"code": "missing_sale_accounting", "message": f"{order.order_number} has no sale journal"})
        elif posts > 1:
            issues.append({"code": "duplicate_sale_accounting", "message": f"{order.order_number} has {posts} sale journals"})
        if posts and order.cogs_total <= ZERO:
            issues.append({"code": "missing_cogs", "message": f"{order.order_number} has no COGS"})

    for payment in Payment.objects.filter(status=Payment.Status.PAID):
        if not AccountingPosting.objects.filter(event_key=f"payment_paid:{payment.pk}").exists():
            issues.append({"code": "payment_without_accounting", "message": f"Payment {payment.pk} is paid without journal"})

    for ret in ReturnRequest.objects.filter(
        status__in=[
            ReturnRequest.Status.RECEIVED,
            ReturnRequest.Status.INSPECTED,
            ReturnRequest.Status.REFUND_PENDING,
            ReturnRequest.Status.REFUNDED,
            ReturnRequest.Status.COMPLETED,
        ]
    ):
        if not AccountingPosting.objects.filter(event_key__startswith=f"return_revenue:{ret.order_id}:{ret.pk}").exists():
            issues.append({"code": "refund_without_reversal", "message": f"{ret.return_number} has no return journal"})

    for grn in GRN.objects.filter(status=GRN.Status.APPROVED):
        if not InventoryCostLayer.objects.filter(grn=grn).exists():
            issues.append({"code": "grn_without_cost_layer", "message": f"{grn.grn_number} has no cost layer"})
        if not AccountingPosting.objects.filter(event_key=f"grn_approved:{grn.pk}").exists():
            issues.append({"code": "grn_without_accounting", "message": f"{grn.grn_number} has no purchase journal"})

    negatives = InventoryCostLayer.objects.filter(remaining_qty__lt=0)
    for layer in negatives:
        issues.append({"code": "negative_cost_layer", "message": f"Layer {layer.pk} remaining {layer.remaining_qty}"})

    for journal in JournalEntry.objects.filter(status=JournalEntry.Status.POSTED):
        debit = journal.total_debit
        credit = journal.total_credit
        if debit != credit:
            issues.append({"code": "unbalanced_journal", "message": f"{journal.number} debit {debit} credit {credit}"})

    for product in Product.objects.filter(is_active=True):
        if not (product.barcode or "").strip():
            issues.append({"code": "barcode_missing", "message": f"{product.sku} is active without a barcode"})

    dupes = (
        Product.objects.exclude(barcode="")
        .values("barcode")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for row in dupes:
        issues.append({"code": "duplicate_barcode", "message": f"Barcode {row['barcode']} is used {row['c']} times"})

    return issues
