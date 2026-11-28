from django.db import migrations


def _update_public_urls(apps, schema_editor, *, reverse=False):
    endpoints = apps.get_model("deployment", "Endpoint").objects.using(schema_editor.connection.alias)
    rows = endpoints.order_by("pk").values_list(
        "pk",
        "public_url",
        "deployment__version__public_id",
        "deployment__version__project__public_id",
        "deployment__version__project__owner__tenant_id",
    )
    for pk, public_url, version_id, project_id, tenant_id in rows.iterator():
        previous_path = f"/{tenant_id}/models/{project_id}/{version_id}"
        version_path = f"/model-versions/{version_id}"
        source, target = (version_path, previous_path) if reverse else (previous_path, version_path)
        base_url = public_url.rstrip("/").removesuffix("/predict")
        if base_url.endswith(source):
            endpoints.filter(pk=pk, public_url=public_url).update(public_url=f"{base_url.removesuffix(source)}{target}")


def update_public_urls(apps, schema_editor):
    _update_public_urls(apps, schema_editor)


def restore_public_urls(apps, schema_editor):
    _update_public_urls(apps, schema_editor, reverse=True)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_initial"),
        ("deployment", "0002_initial"),
    ]

    operations = [migrations.RunPython(update_public_urls, restore_public_urls)]
