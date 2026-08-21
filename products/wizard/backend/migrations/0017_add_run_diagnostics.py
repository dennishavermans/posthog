from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0016_create_wizard_worker"),
    ]

    operations = [
        migrations.AddField(
            model_name="wizardrun",
            name="deadline_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="error_message",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="finished_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="stage",
            field=models.CharField(
                blank=True,
                choices=[
                    ("dispatching", "dispatching"),
                    ("provisioning", "provisioning"),
                    ("preparing_workspace", "preparing_workspace"),
                    ("executing_wizard", "executing_wizard"),
                    ("creating_artifacts", "creating_artifacts"),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="stage_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="wizardrun",
            name="error_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("timeout", "timeout"),
                    ("provisioning_failed", "provisioning_failed"),
                    ("repository_access_failed", "repository_access_failed"),
                    ("workspace_preparation_failed", "workspace_preparation_failed"),
                    ("execution_failed", "execution_failed"),
                    ("artifact_creation_failed", "artifact_creation_failed"),
                    ("dispatch_failed", "dispatch_failed"),
                ],
                max_length=50,
                null=True,
            ),
        ),
    ]
