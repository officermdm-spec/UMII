from django.db import migrations


def grant_new_modules(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(user_type="staff", is_superuser=False).iterator():
        modules = list(user.allowed_modules or [])
        if not modules:
            continue
        changed = False
        if "accounting" in modules:
            if "expenses" not in modules:
                modules.append("expenses")
                changed = True
            if "vendor_payments" not in modules:
                modules.append("vendor_payments")
                changed = True
        if "payments" in modules and "payment_methods" not in modules:
            modules.append("payment_methods")
            changed = True
        if changed:
            user.allowed_modules = modules
            user.save(update_fields=["allowed_modules"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_grant_warehouse_brand_modules"),
    ]

    operations = [
        migrations.RunPython(grant_new_modules, migrations.RunPython.noop),
    ]
