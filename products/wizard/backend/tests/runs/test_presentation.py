from uuid import UUID

from posthog.test.base import APIBaseTest
from unittest.mock import patch

from parameterized import parameterized
from rest_framework import status

from posthog.models import Team

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import CreateWizardRunInput, LocalFolderWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.models import WizardRun


class TestWizardRunViewSet(APIBaseTest):
    def _url(self, run_id: str = "") -> str:
        return f"/api/projects/{self.team.id}/wizard/runs/{run_id}"

    def test_create_local_run(self) -> None:
        response = self.client.post(
            self._url(),
            {
                "environment": "local",
                "workspace": {"type": "local_folder", "project_name": "example-project"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.json(),
            {
                "id": response.json()["id"],
                "team_id": self.team.id,
                "created_by_id": self.user.id,
                "environment": "local",
                "workspace": {"type": "local_folder", "project_name": "example-project"},
                "status": "running",
                "error_code": None,
            },
        )

    def test_retrieve_run(self) -> None:
        created = self.client.post(
            self._url(),
            {
                "environment": "local",
                "workspace": {"type": "local_folder", "project_name": "example-project"},
            },
            format="json",
        ).json()

        response = self.client.get(self._url(created["id"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), created)

    def test_retrieve_does_not_disclose_another_teams_run(self) -> None:
        other_team = Team.objects.create(
            organization=self.team.organization,
            project=self.team.project,
            name="Other environment",
        )
        other_run = wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=other_team.id,
                created_by_id=self.user.id,
                environment=WizardRunEnvironment.LOCAL,
                workspace=LocalFolderWorkspace(project_name="other-project"),
            )
        )

        response = self.client.get(self._url(str(other_run.id)))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_rejects_unknown_workspace_without_writing(self) -> None:
        response = self.client.post(
            self._url(),
            {"environment": "local", "workspace": {"type": "unknown"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(WizardRun.objects.unscoped().filter(team_id=self.team.id).exists())

    def test_create_rejects_environment_workspace_mismatch(self) -> None:
        response = self.client.post(
            self._url(),
            {
                "environment": "local",
                "workspace": {"type": "git_repository", "repository": "posthog/posthog"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], "Choose a workspace supported by this run environment.")

    @parameterized.expand(("missing_integration", "inaccessible_repository"))
    def test_cloud_repository_admission_has_one_public_error(self, scenario: str) -> None:
        integration_id = None if scenario == "missing_integration" else 123
        with (
            patch(
                "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration_id",
                return_value=integration_id,
            ),
            patch(
                "products.wizard.backend.logic.runs.repo_selection.repository_accessible_via_integration",
                return_value=False,
            ),
        ):
            response = self.client.post(
                self._url(),
                {
                    "environment": "cloud",
                    "workspace": {"type": "git_repository", "repository": "posthog/posthog"},
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["detail"], "Connect GitHub with access to this repository, then try again.")

    @patch("products.wizard.backend.logic.artifacts.object_storage.write")
    def test_list_run_artifacts(self, _write) -> None:
        created = self.client.post(
            self._url(),
            {
                "environment": "local",
                "workspace": {"type": "local_folder", "project_name": "example-project"},
            },
            format="json",
        ).json()
        wizard_facade.create_git_diff_artifact(self.team.id, UUID(created["id"]), b"diff")

        response = self.client.get(self._url(f"{created['id']}/artifacts/"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["run_id"], created["id"])
        self.assertEqual(response.json()[0]["artifact_type"], "git_diff")
