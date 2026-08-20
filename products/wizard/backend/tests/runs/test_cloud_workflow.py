import asyncio
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock

from temporalio.exceptions import ActivityError, ApplicationError, RetryState, TimeoutError, TimeoutType

from products.wizard.backend.facade.enums import WizardRunErrorCode, WizardWorkspaceType
from products.wizard.backend.temporal.activities.execution import WIZARD_WORKER_TIMEOUT_ERROR_TYPE, execute_wizard
from products.wizard.backend.temporal.activities.handoff import create_run_artifacts
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.activities.workspace import clone_repository, destroy_worker, provision_worker
from products.wizard.backend.temporal.contracts import (
    PreparedGitRepositoryWorkspace,
    ProvisionedWizardWorker,
    WizardRunActivityInput,
    WizardRunFailureActivityInput,
)
from products.wizard.backend.temporal.workflows import execute_run as execute_run_workflow_module
from products.wizard.backend.temporal.workflows.execute_run import ExecuteWizardRunWorkflow


def _activity_error(cause: BaseException) -> ActivityError:
    error = ActivityError(
        "Activity failed",
        scheduled_event_id=1,
        started_event_id=2,
        identity="worker",
        activity_type="wizard_execute",
        activity_id="activity",
        retry_state=RetryState.MAXIMUM_ATTEMPTS_REACHED,
    )
    error.__cause__ = cause
    return error


@pytest.fixture
def workflow_input() -> WizardRunActivityInput:
    return WizardRunActivityInput(team_id=1, run_id=uuid4())


@pytest.fixture
def worker(workflow_input: WizardRunActivityInput) -> ProvisionedWizardWorker:
    return ProvisionedWizardWorker(
        team_id=workflow_input.team_id,
        run_id=workflow_input.run_id,
        sandbox_id="worker",
        workspace_type=WizardWorkspaceType.GIT_REPOSITORY,
    )


@pytest.fixture
def workspace(
    workflow_input: WizardRunActivityInput,
    worker: ProvisionedWizardWorker,
) -> PreparedGitRepositoryWorkspace:
    return PreparedGitRepositoryWorkspace(
        team_id=workflow_input.team_id,
        run_id=workflow_input.run_id,
        sandbox_id=worker.sandbox_id,
        repository="posthog/posthog",
        root_path="/tmp/workspace/repos/posthog/posthog",
        github_integration_id=123,
    )


@pytest.mark.asyncio
async def test_cloud_workflow_completes_after_worker_execution(
    monkeypatch: pytest.MonkeyPatch,
    workflow_input: WizardRunActivityInput,
    worker: ProvisionedWizardWorker,
    workspace: PreparedGitRepositoryWorkspace,
) -> None:
    execute_activity = AsyncMock(side_effect=[None, worker, workspace, None, None, None, None])
    monkeypatch.setattr(execute_run_workflow_module.workflow, "execute_activity", execute_activity)

    await ExecuteWizardRunWorkflow().run(workflow_input)

    assert [call.args[0] for call in execute_activity.await_args_list] == [
        start_run,
        provision_worker,
        clone_repository,
        execute_wizard,
        create_run_artifacts,
        destroy_worker,
        complete_run,
    ]
    assert execute_activity.await_args_list[0].args[1] == workflow_input
    assert execute_activity.await_args_list[1].args[1] == workflow_input
    assert execute_activity.await_args_list[2].args[1] == worker
    assert execute_activity.await_args_list[3].args[1] == workspace
    assert execute_activity.await_args_list[4].args[1] == workspace
    assert execute_activity.await_args_list[5].args[1] == worker
    assert execute_activity.await_args_list[6].args[1] == workflow_input
    assert execute_activity.await_args_list[0].kwargs["retry_policy"].maximum_attempts == 3
    assert execute_activity.await_args_list[1].kwargs["retry_policy"].maximum_attempts == 1
    assert execute_activity.await_args_list[2].kwargs["retry_policy"].maximum_attempts == 1
    assert execute_activity.await_args_list[3].kwargs["retry_policy"].maximum_attempts == 1
    assert execute_activity.await_args_list[4].kwargs["retry_policy"].maximum_attempts == 1
    assert execute_activity.await_args_list[5].kwargs["retry_policy"].maximum_attempts == 3
    assert execute_activity.await_args_list[6].kwargs["retry_policy"].maximum_attempts == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cause", "expected_error_code"),
    [
        (
            ApplicationError("Wizard Worker timed out.", type=WIZARD_WORKER_TIMEOUT_ERROR_TYPE),
            WizardRunErrorCode.TIMEOUT,
        ),
        (
            TimeoutError("Activity timed out", type=TimeoutType.START_TO_CLOSE, last_heartbeat_details=[]),
            WizardRunErrorCode.TIMEOUT,
        ),
        (ApplicationError("Worker failed", type="WorkerFailure"), WizardRunErrorCode.EXECUTION_FAILED),
    ],
)
async def test_cloud_workflow_persists_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
    workflow_input: WizardRunActivityInput,
    worker: ProvisionedWizardWorker,
    workspace: PreparedGitRepositoryWorkspace,
    cause: BaseException,
    expected_error_code: WizardRunErrorCode,
) -> None:
    activity_error = _activity_error(cause)
    execute_activity = AsyncMock(side_effect=[None, worker, workspace, activity_error, None, None])
    monkeypatch.setattr(execute_run_workflow_module.workflow, "execute_activity", execute_activity)

    with pytest.raises(ActivityError) as raised:
        await ExecuteWizardRunWorkflow().run(workflow_input)

    assert raised.value is activity_error
    assert execute_activity.await_args_list[4].args == (destroy_worker, worker)
    assert execute_activity.await_args_list[5].args == (
        fail_run,
        WizardRunFailureActivityInput(
            team_id=workflow_input.team_id,
            run_id=workflow_input.run_id,
            error_code=expected_error_code,
        ),
    )


@pytest.mark.asyncio
async def test_cloud_workflow_persists_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    workflow_input: WizardRunActivityInput,
    worker: ProvisionedWizardWorker,
    workspace: PreparedGitRepositoryWorkspace,
) -> None:
    execute_activity = AsyncMock(side_effect=[None, worker, workspace, asyncio.CancelledError(), None, None])
    monkeypatch.setattr(execute_run_workflow_module.workflow, "execute_activity", execute_activity)

    with pytest.raises(asyncio.CancelledError):
        await ExecuteWizardRunWorkflow().run(workflow_input)

    assert execute_activity.await_args_list[4].args == (destroy_worker, worker)
    assert execute_activity.await_args_list[5].args == (cancel_run, workflow_input)


def test_cloud_workflow_identity_and_input_parsing() -> None:
    run_id = uuid4()

    assert ExecuteWizardRunWorkflow.workflow_id_for(run_id) == f"wizard-run-{run_id}"
    assert ExecuteWizardRunWorkflow.parse_inputs([f'{{"team_id": 1, "run_id": "{run_id}"}}']) == WizardRunActivityInput(
        team_id=1,
        run_id=UUID(str(run_id)),
    )
