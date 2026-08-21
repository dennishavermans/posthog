from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0014_add_run_idempotency_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="wizardrun",
            name="dispatch_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="dispatch_error",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="dispatch_status",
            field=models.CharField(
                blank=True,
                choices=[("pending", "pending"), ("dispatched", "dispatched")],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="workflow_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
