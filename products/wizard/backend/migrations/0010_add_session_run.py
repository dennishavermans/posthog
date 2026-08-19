import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0009_add_dispatch_failed_error_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="wizardsession",
            name="run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessions",
                to="wizard.wizardrun",
            ),
        ),
    ]
