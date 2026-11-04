from django.db import migrations


UNUSED_ACCOUNTS = [
    ("3000", "Owner Capital", "equity"),
    ("3100", "Retained Earnings", "equity"),
]


def remove_unreferenced_accounts(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    JournalLine = apps.get_model("accounting", "JournalLine")
    database = schema_editor.connection.alias

    for code, _name, _account_type in UNUSED_ACCOUNTS:
        account = Account.objects.using(database).filter(code=code).first()
        if account and not JournalLine.objects.using(database).filter(
            account_id=account.pk
        ).exists():
            account.delete(using=database)


def restore_accounts(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    database = schema_editor.connection.alias

    for code, name, account_type in UNUSED_ACCOUNTS:
        Account.objects.using(database).get_or_create(
            code=code,
            defaults={
                "name": name,
                "account_type": account_type,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0006_rename_legacy_order_discount_account"),
    ]

    operations = [
        migrations.RunPython(remove_unreferenced_accounts, restore_accounts),
    ]
