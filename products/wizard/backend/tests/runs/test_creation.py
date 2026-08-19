import pytest
from unittest.mock import patch

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import CreateWizardRunInput, GitRepositoryWorkspace, LocalFolderWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunStatus
from products.wizard.backend.facade.errors import (
    InvalidRepositoryError,
    InvalidWorkspaceEnvironmentError,
    MissingGitHubIntegrationError,
    RepositoryNotAccessibleError,
)
from products.wizard.backend.models import WizardRun


@pytest.mark.django_db
def test_local_run_starts_running(team, user) -> None:
    run = wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team.id,
            created_by_id=user.id,
            environment=WizardRunEnvironment.LOCAL,
            workspace=LocalFolderWorkspace(project_name="example-project"),
        )
    )

    assert run.team_id == team.id
    assert run.created_by_id == user.id
    assert run.environment == WizardRunEnvironment.LOCAL
    assert run.workspace == LocalFolderWorkspace(project_name="example-project")
    assert run.status == WizardRunStatus.RUNNING
    assert run.error_code is None


@pytest.mark.django_db
def test_create_run_rejects_unsupported_environment_workspace(team, user) -> None:
    with pytest.raises(InvalidWorkspaceEnvironmentError):
        wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team.id,
                created_by_id=user.id,
                environment=WizardRunEnvironment.LOCAL,
                workspace=GitRepositoryWorkspace(repository="posthog/posthog"),
            )
        )

    assert not WizardRun.objects.for_team(team.id).exists()


@pytest.mark.django_db
def test_cloud_run_starts_created(team, user) -> None:
    with (
        patch(
            "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration_id",
            return_value=123,
        ),
        patch(
            "products.wizard.backend.logic.runs.repo_selection.repository_accessible_via_integration",
            return_value=True,
        ),
    ):
        run = wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team.id,
                created_by_id=user.id,
                environment=WizardRunEnvironment.CLOUD,
                workspace=GitRepositoryWorkspace(repository="posthog/posthog"),
            )
        )

    assert run.status == WizardRunStatus.CREATED
    assert run.workspace == GitRepositoryWorkspace(repository="posthog/posthog")


@pytest.mark.django_db
def test_cloud_run_requires_github_integration(team, user) -> None:
    with patch(
        "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration_id",
        return_value=None,
    ):
        with pytest.raises(MissingGitHubIntegrationError):
            wizard_facade.create_run(
                CreateWizardRunInput(
                    team_id=team.id,
                    created_by_id=user.id,
                    environment=WizardRunEnvironment.CLOUD,
                    workspace=GitRepositoryWorkspace(repository="posthog/posthog"),
                )
            )

    assert not WizardRun.objects.for_team(team.id).exists()


@pytest.mark.django_db
def test_cloud_run_rejects_inaccessible_repository(team, user) -> None:
    with (
        patch(
            "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration_id",
            return_value=123,
        ),
        patch(
            "products.wizard.backend.logic.runs.repo_selection.repository_accessible_via_integration",
            return_value=False,
        ),
    ):
        with pytest.raises(RepositoryNotAccessibleError):
            wizard_facade.create_run(
                CreateWizardRunInput(
                    team_id=team.id,
                    created_by_id=user.id,
                    environment=WizardRunEnvironment.CLOUD,
                    workspace=GitRepositoryWorkspace(repository="private/example"),
                )
            )


@pytest.mark.parametrize("repository", ("posthog", "/posthog", "posthog/", "posthog/posthog/extra"))
@pytest.mark.django_db
def test_cloud_run_rejects_invalid_repository_before_github_lookup(team, user, repository: str) -> None:
    with patch("products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration_id") as resolve:
        with pytest.raises(InvalidRepositoryError):
            wizard_facade.create_run(
                CreateWizardRunInput(
                    team_id=team.id,
                    created_by_id=user.id,
                    environment=WizardRunEnvironment.CLOUD,
                    workspace=GitRepositoryWorkspace(repository=repository),
                )
            )

    resolve.assert_not_called()
    assert not WizardRun.objects.for_team(team.id).exists()
