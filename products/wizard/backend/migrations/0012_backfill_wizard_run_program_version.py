from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("wizard", "0011_add_wizard_run_program"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                UPDATE wizard_wizardrun
                SET program = jsonb_set(program, '{wizard_version}', '"latest"'::jsonb, true)
                WHERE NOT (program ? 'wizard_version')
            """,
            reverse_sql="""
                UPDATE wizard_wizardrun
                SET program = program - 'wizard_version'
                WHERE program ->> 'wizard_version' = 'latest'
            """,
        ),
    ]
