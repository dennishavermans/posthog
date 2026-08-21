import django.db.models.deletion
from django.db import migrations, models

import posthog.uuidt


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0015_add_run_dispatch_state"),
    ]

    operations = [
        migrations.CreateModel(
            name="WizardWorker",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True, null=True)),
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
                    "sandbox_id",
                    models.CharField(blank=True, max_length=255, null=True, unique=True),
                ),
                (
                    "cleanup_status",
                    models.CharField(
                        choices=[
                            ("active", "active"),
                            ("pending", "pending"),
                            ("cleaned", "cleaned"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("cleanup_attempts", models.PositiveSmallIntegerField(default=0)),
                (
                    "cleanup_error",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("cleaned_at", models.DateTimeField(blank=True, null=True)),
                (
                    "run",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="worker",
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
            },
        ),
    ]
