from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0008_add_execution_failed_error_code"),
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
                    ("dispatch_failed", "dispatch_failed"),
                ],
                max_length=50,
                null=True,
            ),
        ),
    ]
