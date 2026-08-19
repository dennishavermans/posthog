import django.db.models.deletion
from django.db import migrations, models

import posthog.uuidt


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1306_add_youtube_analytics_integration_kind"),
        ("wizard", "0006_create_wizard_run"),
    ]

    operations = [
        migrations.CreateModel(
            name="WizardRunArtifact",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=posthog.uuidt.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "type",
                    models.CharField(choices=[("git_diff", "git_diff")], max_length=30),
                ),
                ("storage_path", models.CharField(max_length=1024)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("content_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="artifacts",
                        to="wizard.wizardrun",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="posthog.team",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "type"),
                        name="unique_wizard_artifact_type_per_run",
                    )
                ],
            },
        ),
    ]
