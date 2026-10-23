from django.db import migrations


def grant_new_modules(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(user_type="staff", is_superuser=False).iterator():
        modules = list(user.allowed_modules or [])
        if not modules:
            continue
        changed = False
        if "inventory" in modules and "warehouses" not in modules:
            modules.append("warehouses")
            changed = True
        if "products" in modules and "brands" not in modules:
            modules.append("brands")
            changed = True
        if changed:
            user.allowed_modules = modules
            user.save(update_fields=["allowed_modules"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_allowed_modules_remove_roles"),
    ]

    operations = [
        migrations.RunPython(grant_new_modules, migrations.RunPython.noop),
    ]
