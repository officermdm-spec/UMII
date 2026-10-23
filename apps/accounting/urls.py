from django.urls import path

from apps.accounting import views

app_name = "accounting"

urlpatterns = [
    path("", views.AccountingDashboardView.as_view(), name="dashboard"),
    path("sales/", views.SalesListView.as_view(), name="sales"),
    path("sales/<int:pk>/", views.SaleDetailView.as_view(), name="sale_detail"),
    path("purchases/", views.PurchaseListView.as_view(), name="purchases"),
    path("expenses/", views.ExpenseListView.as_view(), name="expenses"),
    path("expenses/add/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/delete/", views.ExpenseDeleteView.as_view(), name="expense_delete"),
    path("income/", views.OtherIncomeListView.as_view(), name="income"),
    path("income/add/", views.OtherIncomeCreateView.as_view(), name="income_create"),
    path("income/<int:pk>/edit/", views.OtherIncomeUpdateView.as_view(), name="income_update"),
    path("income/<int:pk>/delete/", views.OtherIncomeDeleteView.as_view(), name="income_delete"),
    path("cash-bank/", views.CashBankView.as_view(), name="cash_bank"),
    path("receivables/", views.ReceivablesView.as_view(), name="receivables"),
    path("payables/", views.PayablesView.as_view(), name="payables"),
    path("ledger/", views.LedgerView.as_view(), name="ledger"),
    path("ledger/export/", views.LedgerExportView.as_view(), name="ledger_export"),
    path("reports/", views.ReportView.as_view(), name="reports"),
    path("reports/<slug:slug>/", views.ReportView.as_view(), name="report"),
    path("reconciliation/", views.ReconciliationView.as_view(), name="reconciliation"),
    path("customers/statement/", views.CustomerStatementView.as_view(), name="customer_statement"),
    path("vendors/statement/", views.VendorStatementView.as_view(), name="vendor_statement"),
]
