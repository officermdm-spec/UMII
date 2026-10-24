from django.contrib import messages
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView, ListView, RedirectView, TemplateView, UpdateView, View

from apps.accounting.coa import BANK, CASH, WALLET, ZERO, money
from apps.accounting.dates import parse_date_range
from apps.accounting.forms import ExpenseForm, OtherIncomeForm
from apps.accounting.models import Expense, JournalEntry, JournalLine, OtherIncome, VendorPayment
from apps.accounting.reconcile import run_reconciliation
from apps.accounting.services import (
    account_balance,
    ensure_accounts,
    period_totals,
    post_expense_event,
    post_other_income_event,
    reverse_event,
)
from apps.accounts.mixins import ModulePermissionMixin, SafeDeleteMixin
from apps.accounts.permissions import MODULES, has_module_permission
from apps.inventory.costing import layer_value, wac_inventory_value
from apps.inventory.models import InventoryCostLayer
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.purchases.models import GRN
from apps.returns.models import ReturnRequest
from apps.vendors.models import Vendor


class AccountingMixin(ModulePermissionMixin):
    module = MODULES.ACCOUNTING

    def dispatch(self, request, *args, **kwargs):
        ensure_accounts()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end, preset = parse_date_range(self.request)
        context["range_start"] = start
        context["range_end"] = end
        context["range_preset"] = preset
        user = self.request.user
        context["can_accounting"] = has_module_permission(user, MODULES.ACCOUNTING)
        context["can_expenses"] = has_module_permission(user, MODULES.EXPENSES)
        context["can_vendor_payments"] = has_module_permission(user, MODULES.VENDOR_PAYMENTS)
        return context


class AccountingDashboardView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = context["range_start"], context["range_end"]
        from django.utils import timezone

        today = timezone.localdate()
        context["today_totals"] = period_totals(today, today)
        context["totals"] = period_totals(start, end)
        context["inventory_value"] = wac_inventory_value()
        context["fifo_inventory_value"] = layer_value()
        return context


class ExpenseListView(AccountingMixin, ListView):
    module = MODULES.EXPENSES
    model = Expense
    template_name = "staff/accounting/expenses.html"
    context_object_name = "expenses"
    paginate_by = 20

    def get_queryset(self):
        qs = Expense.objects.all()
        q = self.request.GET.get("q")
        start, end, _ = parse_date_range(self.request)
        qs = qs.filter(date__gte=start, date__lte=end)
        if q:
            qs = qs.filter(Q(category__icontains=q) | Q(reference__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total"] = self.get_queryset().aggregate(s=Sum("amount"))["s"] or ZERO
        return context


class ExpenseCreateView(AccountingMixin, CreateView):
    module = MODULES.EXPENSES
    form_class = ExpenseForm
    template_name = "staff/accounting/expense_form.html"
    success_url = reverse_lazy("accounting:expenses")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        post_expense_event(self.object, self.request.user)
        messages.success(self.request, "Expense posted.")
        return redirect(self.success_url)


class ExpenseUpdateView(AccountingMixin, UpdateView):
    module = MODULES.EXPENSES
    model = Expense
    form_class = ExpenseForm
    template_name = "staff/accounting/expense_form.html"
    success_url = reverse_lazy("accounting:expenses")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for name in ("amount", "category", "payment_account", "date"):
            form.fields[name].disabled = True
        return form

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, "Expense details updated.")
        return redirect(self.success_url)


class ExpenseDeleteView(SafeDeleteMixin, AccountingMixin, DeleteView):
    module = MODULES.EXPENSES
    model = Expense
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("accounting:expenses")
    delete_success_message = "Expense deleted and ledger reversed."

    def form_valid(self, form):
        reverse_event(f"expense:{self.object.pk}", self.request.user, reason=f"Delete expense {self.object.pk}")
        return super().form_valid(form)


class OtherIncomeListView(AccountingMixin, ListView):
    model = OtherIncome
    template_name = "staff/accounting/income.html"
    context_object_name = "incomes"
    paginate_by = 20

    def get_queryset(self):
        qs = OtherIncome.objects.all()
        start, end, _ = parse_date_range(self.request)
        q = self.request.GET.get("q")
        qs = qs.filter(date__gte=start, date__lte=end)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(reference__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total"] = self.get_queryset().aggregate(s=Sum("amount"))["s"] or ZERO
        return context


class OtherIncomeCreateView(AccountingMixin, CreateView):
    form_class = OtherIncomeForm
    template_name = "staff/accounting/income_form.html"
    success_url = reverse_lazy("accounting:income")

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.created_by = self.request.user
        self.object.save()
        post_other_income_event(self.object, self.request.user)
        messages.success(self.request, "Other income posted.")
        return redirect(self.success_url)


class OtherIncomeUpdateView(AccountingMixin, UpdateView):
    model = OtherIncome
    form_class = OtherIncomeForm
    template_name = "staff/accounting/income_form.html"
    success_url = reverse_lazy("accounting:income")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for name in ("amount", "payment_account", "date"):
            form.fields[name].disabled = True
        return form

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, "Other income details updated.")
        return redirect(self.success_url)


class OtherIncomeDeleteView(SafeDeleteMixin, AccountingMixin, DeleteView):
    model = OtherIncome
    template_name = "staff/confirm_delete.html"
    success_url = reverse_lazy("accounting:income")
    delete_success_message = "Other income deleted and ledger reversed."

    def form_valid(self, form):
        reverse_event(
            f"other_income:{self.object.pk}",
            self.request.user,
            reason=f"Delete other income {self.object.pk}",
        )
        return super().form_valid(form)


class LedgerView(AccountingMixin, ListView):
    model = JournalEntry
    template_name = "staff/accounting/ledger.html"
    context_object_name = "journals"
    paginate_by = 25

    def get_queryset(self):
        qs = JournalEntry.objects.prefetch_related("lines__account")
        start, end, _ = parse_date_range(self.request)
        q = self.request.GET.get("q")
        qs = qs.filter(entry_at__date__gte=start, entry_at__date__lte=end)
        if q:
            qs = qs.filter(
                Q(number__icontains=q) | Q(description__icontains=q) | Q(reference_id__icontains=q)
            )
        return qs


class SalesListView(AccountingMixin, ListView):
    model = Order
    template_name = "staff/accounting/sales.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related("customer", "fulfillment_warehouse").exclude(
            status__in=[Order.Status.PENDING, Order.Status.CANCELLED]
        )
        start, end, _ = parse_date_range(self.request)
        q = self.request.GET.get("q")
        qs = qs.filter(created_at__date__gte=start, created_at__date__lte=end)
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q)
                | Q(customer__username__icontains=q)
                | Q(billing_full_name__icontains=q)
            )
        return qs


class SaleDetailView(AccountingMixin, DetailView):
    model = Order
    template_name = "staff/accounting/sale_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("customer", "fulfillment_warehouse").prefetch_related(
            "items", "payments", "return_requests"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        paid = order.payments.filter(status=Payment.Status.PAID).aggregate(s=Sum("amount"))["s"] or ZERO
        refunded = (
            order.payments.filter(status=Payment.Status.REFUNDED).aggregate(s=Sum("amount"))["s"] or ZERO
        )
        gross = money(sum((item.unit_price * item.quantity for item in order.items.all()), ZERO))
        net = money(gross - order.catalog_discount - order.offer_discount - order.discount)
        context["gross"] = gross
        context["net_sales"] = net
        context["paid"] = paid
        context["refunded"] = refunded
        context["outstanding"] = money(order.grand_total - paid)
        context["gross_profit"] = money(net - order.cogs_total)
        return context


class PurchaseListView(AccountingMixin, ListView):
    model = GRN
    template_name = "staff/accounting/purchases.html"
    context_object_name = "grns"
    paginate_by = 20

    def get_queryset(self):
        qs = GRN.objects.filter(status=GRN.Status.APPROVED).select_related("vendor", "warehouse")
        start, end, _ = parse_date_range(self.request)
        q = self.request.GET.get("q")
        qs = qs.filter(approved_at__date__gte=start, approved_at__date__lte=end)
        if q:
            qs = qs.filter(Q(grn_number__icontains=q) | Q(vendor__name__icontains=q))
        return qs


class CashBankView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/cash_bank.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start, end = context["range_start"], context["range_end"]
        context["cash"] = account_balance(CASH, start, end)
        context["bank"] = account_balance(BANK, start, end)
        context["wallet"] = account_balance(WALLET, start, end)
        context["lines"] = (
            JournalLine.objects.filter(
                account__code__in=[CASH, BANK, WALLET],
                journal__status=JournalEntry.Status.POSTED,
                journal__entry_at__date__gte=start,
                journal__entry_at__date__lte=end,
            )
            .select_related("journal", "account")
            .order_by("-journal__entry_at")[:200]
        )
        return context


class ReceivablesView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/receivables.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = []
        for order in Order.objects.exclude(
            status__in=[Order.Status.PENDING, Order.Status.CANCELLED]
        ).select_related("customer").prefetch_related("payments"):
            paid = order.payments.filter(status=Payment.Status.PAID).aggregate(s=Sum("amount"))["s"] or ZERO
            outstanding = money(order.grand_total - paid)
            if outstanding > ZERO:
                rows.append({"order": order, "outstanding": outstanding})
        context["rows"] = rows
        context["total"] = sum((row["outstanding"] for row in rows), ZERO)
        return context


class PayablesView(AccountingMixin, RedirectView):
    module = MODULES.VENDOR_PAYMENTS
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("vendor_payments:list")

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class ReportView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/report.html"
    report_slug = "profit-loss"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug") or self.report_slug
        start, end = context["range_start"], context["range_end"]
        context["slug"] = slug
        context["totals"] = period_totals(start, end)
        context["title"] = slug.replace("-", " ").title()
        context["inventory_value"] = wac_inventory_value()
        context["fifo_inventory_value"] = layer_value()
        if slug == "ledger":
            context["journals"] = JournalEntry.objects.filter(
                entry_at__date__gte=start, entry_at__date__lte=end
            ).prefetch_related("lines__account")
        elif slug == "sales":
            context["orders"] = Order.objects.filter(
                created_at__date__gte=start, created_at__date__lte=end
            ).exclude(status__in=[Order.Status.PENDING, Order.Status.CANCELLED])
        elif slug == "purchases":
            context["grns"] = GRN.objects.filter(
                status=GRN.Status.APPROVED, approved_at__date__gte=start, approved_at__date__lte=end
            )
        elif slug == "expenses":
            context["expenses"] = Expense.objects.filter(date__gte=start, date__lte=end)
        elif slug == "cogs":
            context["orders"] = Order.objects.filter(
                created_at__date__gte=start, created_at__date__lte=end, cogs_total__gt=0
            )
        elif slug == "returns-refunds":
            from apps.accounting.models import AccountingPosting

            returns = list(
                ReturnRequest.objects.filter(
                    created_at__date__gte=start, created_at__date__lte=end
                ).select_related("order")
            )
            keys = [f"return_revenue:{row.order_id}:{row.pk}" for row in returns]
            posted = set(
                AccountingPosting.objects.filter(event_key__in=keys).values_list("event_key", flat=True)
            )
            context["returns"] = [
                {
                    "row": row,
                    "posted": f"return_revenue:{row.order_id}:{row.pk}" in posted,
                }
                for row in returns
            ]
            context["returns_total"] = context["totals"]["sales_returns"]
        elif slug == "tax-summary":
            context["tax_total"] = (
                Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
                .exclude(status=Order.Status.CANCELLED)
                .aggregate(s=Sum("tax"))["s"]
                or ZERO
            )
        elif slug == "inventory-valuation":
            from apps.inventory.models import Inventory

            context["wac_rows"] = [
                {
                    "inv": inv,
                    "avg": inv.product.purchase_price,
                    "value": money(inv.current_stock * inv.product.purchase_price),
                }
                for inv in Inventory.objects.select_related("product", "warehouse").filter(
                    current_stock__gt=0
                )
            ]
            context["layers"] = InventoryCostLayer.objects.filter(remaining_qty__gt=0).select_related(
                "product", "warehouse", "grn"
            )
        return context


class ReconciliationView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/reconciliation.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["issues"] = run_reconciliation()
        return context


class CustomerStatementView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/customer_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer_id = self.request.GET.get("customer")
        context["customers"] = (
            Order.objects.order_by("customer__username")
            .values_list("customer_id", "customer__username")
            .distinct()
        )
        context["rows"] = []
        context["balance"] = ZERO
        if customer_id:
            orders = Order.objects.filter(customer_id=customer_id).order_by("created_at")
            balance = ZERO
            rows = []
            for order in orders:
                rows.append(
                    {
                        "date": order.created_at,
                        "label": order.order_number,
                        "debit": order.grand_total,
                        "credit": ZERO,
                    }
                )
                balance = money(balance + order.grand_total)
                for payment in order.payments.filter(status=Payment.Status.PAID):
                    rows.append(
                        {
                            "date": payment.paid_at or payment.created_at,
                            "label": f"Payment {payment.pk}",
                            "debit": ZERO,
                            "credit": payment.amount,
                        }
                    )
                    balance = money(balance - payment.amount)
            context["rows"] = rows
            context["balance"] = balance
            context["selected"] = customer_id
        return context


class VendorStatementView(AccountingMixin, TemplateView):
    template_name = "staff/accounting/vendor_statement.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor_id = self.request.GET.get("vendor")
        context["vendors"] = Vendor.objects.filter(is_active=True)
        context["rows"] = []
        context["balance"] = ZERO
        if vendor_id:
            vendor = get_object_or_404(Vendor, pk=vendor_id)
            balance = ZERO
            rows = []
            for grn in vendor.grns.filter(status=GRN.Status.APPROVED).order_by("approved_at"):
                rows.append(
                    {
                        "date": grn.approved_at,
                        "label": grn.grn_number,
                        "purchase": grn.grand_total,
                        "payment": ZERO,
                    }
                )
                balance = money(balance + grn.grand_total)
            for payment in vendor.vendor_payments.filter(status=VendorPayment.Status.POSTED).order_by("date"):
                rows.append(
                    {
                        "date": payment.date,
                        "label": payment.reference or f"PAY-{payment.pk}",
                        "purchase": ZERO,
                        "payment": payment.amount,
                    }
                )
                balance = money(balance - payment.amount)
            context["vendor"] = vendor
            context["rows"] = rows
            context["balance"] = balance
        return context


class LedgerExportView(AccountingMixin, View):
    def get(self, request):
        start, end, _ = parse_date_range(request)
        lines = JournalLine.objects.filter(
            journal__entry_at__date__gte=start,
            journal__entry_at__date__lte=end,
        ).select_related("journal", "account")
        rows = ["Number,Date,Account,Debit,Credit,Description"]
        for line in lines:
            desc = line.journal.description.replace(",", " ")
            rows.append(
                f"{line.journal.number},{line.journal.entry_at.date()},{line.account.code} {line.account.name},"
                f"{line.debit},{line.credit},{desc}"
            )
        response = HttpResponse("\n".join(rows), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="ledger.csv"'
        return response
