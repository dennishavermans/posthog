from posthog.test.base import TestMigrations

from django.apps.registry import Apps


class TestWizardRunProgramMigration(TestMigrations):
    migrate_from = "0010_support_pull_request_artifacts"
    migrate_to = "0011_add_wizard_run_program"
    CLASS_DATA_LEVEL_SETUP = False

    @property
    def app(self) -> str:
        return "wizard"

    def setUpBeforeMigration(self, apps: Apps) -> None:
        Organization = apps.get_model("posthog", "Organization")
        Project = apps.get_model("posthog", "Project")
        Team = apps.get_model("posthog", "Team")
        User = apps.get_model("posthog", "User")
        WizardRun = apps.get_model("wizard", "WizardRun")

        organization = Organization.objects.create(name="Wizard registry migration")
        project = Project.objects.create(id=987_654, organization=organization, name="Wizard registry migration")
        team = Team.objects.create(organization=organization, project=project, name="Wizard registry migration")
        user = User.objects.create(email="wizard-registry@example.com", distinct_id="wizard-registry-migration")
        self.run_id = WizardRun.objects.create(
            team=team,
            created_by=user,
            environment="local",
            workspace_type="local_folder",
            workspace={"project_name": "example-project"},
            status="running",
        ).id

    def test_backfills_existing_run_before_enforcing_non_null(self) -> None:
        assert self.apps is not None
        WizardRun = self.apps.get_model("wizard", "WizardRun")
        run = WizardRun.objects.get(id=self.run_id)

        assert run.program == {
            "id": "posthog-integration",
            "name": "PostHog integration",
            "description": "Set up PostHog SDK integration",
            "command": [],
            "tags": [],
            "required_programs": [],
            "supported_environments": ["local", "cloud"],
        }
        assert WizardRun._meta.get_field("program").null is False


class TestWizardRunProgramVersionMigration(TestMigrations):
    migrate_from = "0011_add_wizard_run_program"
    migrate_to = "0012_backfill_wizard_run_program_version"
    CLASS_DATA_LEVEL_SETUP = False

    @property
    def app(self) -> str:
        return "wizard"

    def setUpBeforeMigration(self, apps: Apps) -> None:
        Organization = apps.get_model("posthog", "Organization")
        Project = apps.get_model("posthog", "Project")
        Team = apps.get_model("posthog", "Team")
        User = apps.get_model("posthog", "User")
        WizardRun = apps.get_model("wizard", "WizardRun")

        organization = Organization.objects.create(name="Wizard version migration")
        project = Project.objects.create(id=987_655, organization=organization, name="Wizard version migration")
        team = Team.objects.create(organization=organization, project=project, name="Wizard version migration")
        user = User.objects.create(email="wizard-version@example.com", distinct_id="wizard-version-migration")
        self.run_id = WizardRun.objects.create(
            team=team,
            created_by=user,
            environment="local",
            workspace_type="local_folder",
            workspace={"project_name": "example-project"},
            program={
                "id": "posthog-integration",
                "name": "PostHog integration",
                "description": "Set up PostHog SDK integration",
                "command": [],
                "tags": [],
                "required_programs": [],
                "supported_environments": ["local", "cloud"],
            },
            status="running",
        ).id

    def test_backfills_historical_execution_behavior(self) -> None:
        assert self.apps is not None
        WizardRun = self.apps.get_model("wizard", "WizardRun")

        assert WizardRun.objects.get(id=self.run_id).program["wizard_version"] == "latest"
