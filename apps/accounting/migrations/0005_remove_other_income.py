from django.db import migrations


def remove_other_income(apps, schema_editor):
    OtherIncome = apps.get_model("accounting", "OtherIncome")
    Account = apps.get_model("accounting", "Account")
    JournalLine = apps.get_model("accounting", "JournalLine")
    database = schema_editor.connection.alias

    if OtherIncome._meta.db_table in schema_editor.connection.introspection.table_names():
        schema_editor.delete_model(OtherIncome)

    account = Account.objects.using(database).filter(code="4020").first()
    if account and not JournalLine.objects.using(database).filter(account_id=account.pk).exists():
        account.delete(using=database)


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0004_remove_expense_title"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(remove_other_income, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.DeleteModel(name="OtherIncome"),
            ],
        ),
    ]
