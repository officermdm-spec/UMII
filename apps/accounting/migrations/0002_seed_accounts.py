from django.db import migrations


def seed_accounts(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    rows = [
        ("1000", "Cash", "asset"),
        ("1010", "Bank", "asset"),
        ("1020", "Digital Wallet", "asset"),
        ("1100", "Accounts Receivable", "asset"),
        ("1200", "Inventory", "asset"),
        ("2000", "Accounts Payable", "liability"),
        ("2100", "Customer Refund Payable", "liability"),
        ("2200", "Tax Payable", "liability"),
        ("3000", "Owner Capital", "equity"),
        ("3100", "Retained Earnings", "equity"),
        ("4000", "Sales Revenue", "revenue"),
        ("4010", "Shipping Revenue", "revenue"),
        ("4020", "Other Income", "revenue"),
        ("4100", "Product Discounts", "contra_revenue"),
        ("4110", "Product Offer Discounts", "contra_revenue"),
        ("4120", "Coupon Discounts", "contra_revenue"),
        ("4130", "Sales Returns", "contra_revenue"),
        ("5000", "Cost of Goods Sold", "expense"),
        ("5100", "Delivery", "expense"),
        ("5110", "Marketing", "expense"),
        ("5120", "Salaries", "expense"),
        ("5130", "Rent", "expense"),
        ("5140", "Electricity", "expense"),
        ("5150", "Internet", "expense"),
        ("5160", "Packaging", "expense"),
        ("5170", "Maintenance", "expense"),
        ("5180", "Office", "expense"),
        ("5190", "Other Expenses", "expense"),
    ]
    for code, name, account_type in rows:
        Account.objects.get_or_create(
            code=code, defaults={"name": name, "account_type": account_type, "is_active": True}
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_accounts, noop),
    ]
