from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("wizard", "0017_add_run_diagnostics")]

    operations = [
        migrations.AddField(
            model_name="wizardrun",
            name="cancellation_dispatched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="cancellation_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
