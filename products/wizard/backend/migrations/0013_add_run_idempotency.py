from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("posthog", "1306_add_youtube_analytics_integration_kind"),
        ("wizard", "0012_backfill_wizard_run_program_version"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="wizardrun",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="wizardrun",
            name="request_fingerprint",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
