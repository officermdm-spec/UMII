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
    path("receivables/", views.ReceivablesView.as_view(), name="receivables"),
    path("payables/", views.PayablesView.as_view(), name="payables"),
    path("reports/", views.ReportView.as_view(), name="reports"),
    path("reports/<slug:slug>/", views.ReportView.as_view(), name="report"),
    path("reconciliation/", views.ReconciliationView.as_view(), name="reconciliation"),
    path("customers/statement/", views.CustomerStatementView.as_view(), name="customer_statement"),
    path("vendors/statement/", views.VendorStatementView.as_view(), name="vendor_statement"),
]
