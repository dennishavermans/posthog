import pytest
from unittest.mock import MagicMock, patch

from asgiref.sync import async_to_sync
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from products.tasks.backend.facade.repository import RepositoryPullRequest
from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    WizardRunDTO,
    WizardRunGitDiffArtifactDTO,
    WizardRunPullRequestArtifactDTO,
)
from products.wizard.backend.facade.enums import WizardRunArtifactType, WizardRunEnvironment
from products.wizard.backend.logic.cloud_worker import (
    WizardWorkerExecutionError,
    WizardWorkerInput,
    WizardWorkerResult,
    WizardWorkerTimeoutError,
)
from products.wizard.backend.temporal.activities.execute_cloud import (
    WIZARD_REPOSITORY_ACCESS_ERROR_TYPE,
    WIZARD_WORKER_EXECUTION_ERROR_TYPE,
    WIZARD_WORKER_TIMEOUT_ERROR_TYPE,
    execute_cloud_run,
)
from products.wizard.backend.temporal.contracts import WizardRunActivityInput


def _create_cloud_run(team_id: int, user_id: int) -> WizardRunDTO:
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
        return wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team_id,
                created_by_id=user_id,
                environment=WizardRunEnvironment.CLOUD,
                workspace=GitRepositoryWorkspace(repository="posthog/posthog"),
            )
        )


def _run_execute_cloud_activity(input: WizardRunActivityInput) -> None:
    async_to_sync(_run_execute_cloud_activity_async)(input)


async def _run_execute_cloud_activity_async(input: WizardRunActivityInput) -> None:
    await ActivityEnvironment().run(execute_cloud_run, input)


@pytest.mark.django_db(transaction=True)
@patch("products.wizard.backend.logic.artifacts.object_storage.write")
def test_execute_cloud_run_rechecks_access_and_stores_artifacts(_write: MagicMock, team, user) -> None:
    run = _create_cloud_run(team.id, user.id)
    diff = b"diff --git a/a b/a\n"
    pull_request = RepositoryPullRequest(
        repository="posthog/posthog",
        number=123,
        url="https://github.com/posthog/posthog/pull/123",
        head_branch="posthog/wizard-123",
        base_branch="master",
    )

    with (
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.repo_selection.resolve_team_github_integration_id",
            return_value=456,
        ) as resolve_integration,
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.repo_selection.repository_accessible_via_integration",
            return_value=True,
        ) as repository_accessible,
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.cloud_worker.execute_wizard_worker",
            return_value=WizardWorkerResult(diff=diff, pull_request=pull_request),
        ) as execute_worker,
    ):
        _run_execute_cloud_activity(WizardRunActivityInput(team_id=team.id, run_id=run.id))

    resolve_integration.assert_called_once_with(team.id)
    repository_accessible.assert_called_once_with(team.id, 456, "posthog/posthog")
    execute_worker.assert_called_once_with(
        WizardWorkerInput(
            team_id=team.id,
            created_by_id=user.id,
            run_id=run.id,
            github_integration_id=456,
            repository="posthog/posthog",
        )
    )
    artifacts = wizard_facade.list_run_artifacts(team.id, run.id)
    assert {artifact.artifact_type for artifact in artifacts} == {
        WizardRunArtifactType.GIT_DIFF,
        WizardRunArtifactType.PULL_REQUEST,
    }
    git_diff_artifact = next(artifact for artifact in artifacts if isinstance(artifact, WizardRunGitDiffArtifactDTO))
    assert git_diff_artifact.size_bytes == len(diff)
    pull_request_artifact = next(
        artifact for artifact in artifacts if isinstance(artifact, WizardRunPullRequestArtifactDTO)
    )
    assert pull_request_artifact.url == pull_request.url
    assert pull_request_artifact.number == pull_request.number


@pytest.mark.django_db(transaction=True)
def test_execute_cloud_run_rejects_access_revoked_after_creation(team, user) -> None:
    run = _create_cloud_run(team.id, user.id)

    with (
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.repo_selection.resolve_team_github_integration_id",
            return_value=None,
        ),
        patch("products.wizard.backend.temporal.activities.execute_cloud.cloud_worker.execute_wizard_worker") as worker,
        pytest.raises(ApplicationError) as error,
    ):
        _run_execute_cloud_activity(WizardRunActivityInput(team_id=team.id, run_id=run.id))

    assert error.value.type == WIZARD_REPOSITORY_ACCESS_ERROR_TYPE
    worker.assert_not_called()
    assert wizard_facade.list_run_artifacts(team.id, run.id) == []


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "worker_error, error_type",
    (
        (WizardWorkerTimeoutError(), WIZARD_WORKER_TIMEOUT_ERROR_TYPE),
        (WizardWorkerExecutionError("execution", 1), WIZARD_WORKER_EXECUTION_ERROR_TYPE),
    ),
)
def test_execute_cloud_run_maps_worker_error(team, user, worker_error: Exception, error_type: str) -> None:
    run = _create_cloud_run(team.id, user.id)

    with (
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.repo_selection.resolve_team_github_integration_id",
            return_value=456,
        ),
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.repo_selection.repository_accessible_via_integration",
            return_value=True,
        ),
        patch(
            "products.wizard.backend.temporal.activities.execute_cloud.cloud_worker.execute_wizard_worker",
            side_effect=worker_error,
        ),
        pytest.raises(ApplicationError) as error,
    ):
        _run_execute_cloud_activity(WizardRunActivityInput(team_id=team.id, run_id=run.id))

    assert error.value.type == error_type
