from django.db import migrations, models

from posthog.migration_helpers import CreateIndexConcurrently


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("wizard", "0013_add_run_idempotency"),
    ]

    operations = [
        CreateIndexConcurrently(
            index_name="unique_wizard_run_idempotency_key_per_team",
            table_name="wizard_wizardrun",
            columns="(team_id, idempotency_key)",
            unique=True,
            where="WHERE idempotency_key IS NOT NULL",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddConstraint(
                    model_name="wizardrun",
                    constraint=models.UniqueConstraint(
                        fields=["team", "idempotency_key"],
                        condition=models.Q(idempotency_key__isnull=False),
                        name="unique_wizard_run_idempotency_key_per_team",
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
