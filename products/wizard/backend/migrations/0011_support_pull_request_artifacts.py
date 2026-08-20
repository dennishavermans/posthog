from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0010_add_session_run"),
    ]

    operations = [
        migrations.AddField(
            model_name="wizardrunartifact",
            name="external_url",
            field=models.URLField(blank=True, max_length=1024, null=True),
        ),
        migrations.AddField(
            model_name="wizardrunartifact",
            name="metadata",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="wizardrunartifact",
            name="content_hash",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name="wizardrunartifact",
            name="size_bytes",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="wizardrunartifact",
            name="storage_path",
            field=models.CharField(blank=True, max_length=1024, null=True),
        ),
        migrations.AlterField(
            model_name="wizardrunartifact",
            name="type",
            field=models.CharField(
                choices=[("git_diff", "git_diff"), ("pull_request", "pull_request")],
                max_length=30,
            ),
        ),
    ]
