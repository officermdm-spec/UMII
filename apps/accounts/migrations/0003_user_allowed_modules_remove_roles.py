from django.db import migrations, models


def copy_existing_modules(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.all().iterator():
        modules = set(
            user.module_permissions.values_list("module", flat=True)
        )
        if user.role_id:
            modules.update(
                user.role.permissions.values_list("module", flat=True)
            )
        user.allowed_modules = sorted(modules)
        user.save(update_fields=["allowed_modules"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_module_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="allowed_modules",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(copy_existing_modules, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="user",
            name="module_permissions",
        ),
        migrations.RemoveField(
            model_name="user",
            name="role",
        ),
        migrations.DeleteModel(
            name="Role",
        ),
        migrations.DeleteModel(
            name="ModulePermission",
        ),
    ]
