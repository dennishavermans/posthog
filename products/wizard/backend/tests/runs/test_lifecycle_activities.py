from collections.abc import Awaitable, Callable

import pytest
from unittest.mock import patch

from asgiref.sync import async_to_sync
from temporalio.testing import ActivityEnvironment

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    LocalFolderWorkspace,
    WizardRunDTO,
)
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.contracts import WizardRunActivityInput, WizardRunFailureActivityInput


def _create_cloud_run(team_id: int, user_id: int) -> WizardRunDTO:
    with (
        patch(
            "products.wizard.backend.logic.runs.lifecycle.repo_selection.resolve_team_github_integration_id",
            return_value=123,
        ),
        patch(
            "products.wizard.backend.logic.runs.lifecycle.repo_selection.repository_accessible_via_integration",
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


def _run_activity(
    activity: Callable[..., Awaitable[None]],
    input: WizardRunActivityInput | WizardRunFailureActivityInput,
) -> None:
    async_to_sync(_run_activity_async)(activity, input)


async def _run_activity_async(
    activity: Callable[..., Awaitable[None]],
    input: WizardRunActivityInput | WizardRunFailureActivityInput,
) -> None:
    await ActivityEnvironment().run(activity, input)


@pytest.mark.django_db(transaction=True)
def test_start_run_activity_is_retry_safe(team, user) -> None:
    run = _create_cloud_run(team.id, user.id)
    input = WizardRunActivityInput(team_id=team.id, run_id=run.id)

    _run_activity(start_run, input)
    _run_activity(start_run, input)

    assert wizard_facade.get_run(team.id, run.id).status == WizardRunStatus.RUNNING


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "terminal_activity, error_code, expected_status",
    (
        (complete_run, None, WizardRunStatus.COMPLETED),
        (fail_run, WizardRunErrorCode.TIMEOUT, WizardRunStatus.FAILED),
        (fail_run, WizardRunErrorCode.EXECUTION_FAILED, WizardRunStatus.FAILED),
        (cancel_run, None, WizardRunStatus.CANCELLED),
    ),
)
def test_terminal_lifecycle_activity_is_retry_safe(
    team,
    user,
    terminal_activity: Callable[..., Awaitable[None]],
    error_code: WizardRunErrorCode | None,
    expected_status: WizardRunStatus,
) -> None:
    run = _create_cloud_run(team.id, user.id)
    input = WizardRunActivityInput(team_id=team.id, run_id=run.id)
    _run_activity(start_run, input)
    terminal_input = (
        WizardRunFailureActivityInput(team_id=team.id, run_id=run.id, error_code=error_code)
        if error_code is not None
        else input
    )

    _run_activity(terminal_activity, terminal_input)
    _run_activity(terminal_activity, terminal_input)

    persisted = wizard_facade.get_run(team.id, run.id)
    assert persisted.status == expected_status
    assert persisted.error_code == error_code


@pytest.mark.django_db(transaction=True)
def test_lifecycle_activity_rejects_local_run(team, user) -> None:
    run = wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team.id,
            created_by_id=user.id,
            environment=WizardRunEnvironment.LOCAL,
            workspace=LocalFolderWorkspace(project_name="example-project"),
        )
    )

    with pytest.raises(ValueError, match="cloud Wizard run"):
        _run_activity(complete_run, WizardRunActivityInput(team_id=team.id, run_id=run.id))
