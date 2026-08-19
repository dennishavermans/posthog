from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0007_create_wizard_run_artifact"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wizardrun",
            name="error_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("timeout", "timeout"),
                    ("execution_failed", "execution_failed"),
                ],
                max_length=50,
                null=True,
            ),
        ),
    ]
