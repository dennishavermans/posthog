from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

POSTHOG_INTEGRATION_PROGRAM = {
    "id": "posthog-integration",
    "name": "PostHog integration",
    "description": "Set up PostHog SDK integration",
    "command": [],
    "tags": [],
    "required_programs": [],
    "supported_environments": ["local", "cloud"],
}


def backfill_program(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    WizardRun = apps.get_model("wizard", "WizardRun")
    WizardRun.objects.filter(program__isnull=True).update(program=POSTHOG_INTEGRATION_PROGRAM)


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0010_support_pull_request_artifacts"),
    ]

    operations = [
        migrations.AddField(
            model_name="wizardrun",
            name="program",
            field=models.JSONField(null=True),
        ),
        migrations.RunPython(backfill_program, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="wizardrun",
            name="program",
            field=models.JSONField(),
        ),
    ]
