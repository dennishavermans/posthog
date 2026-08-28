from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboards", "0016_dashboardsavedview"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="dashboardsavedview",
            index=models.Index(
                fields=["team", "name", "id"],
                condition=models.Q(scope="team"),
                name="dash_saved_view_team_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="dashboardsavedview",
            index=models.Index(
                fields=["team", "created_by", "name", "id"],
                condition=models.Q(scope="private"),
                name="dash_saved_view_private_idx",
            ),
        ),
    ]
