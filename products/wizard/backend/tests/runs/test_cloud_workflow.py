import asyncio
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock

from temporalio.exceptions import ActivityError, ApplicationError, RetryState, TimeoutError, TimeoutType

from products.wizard.backend.facade.enums import WizardRunErrorCode
from products.wizard.backend.temporal.activities.execute_cloud import (
    WIZARD_WORKER_TIMEOUT_ERROR_TYPE,
    execute_cloud_run,
)
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.contracts import WizardRunActivityInput, WizardRunFailureActivityInput
from products.wizard.backend.temporal.workflows import execute_run as execute_run_workflow_module
from products.wizard.backend.temporal.workflows.execute_run import ExecuteWizardRunWorkflow


def _activity_error(cause: BaseException) -> ActivityError:
    error = ActivityError(
        "Activity failed",
        scheduled_event_id=1,
        started_event_id=2,
        identity="worker",
        activity_type="execute_cloud_run",
        activity_id="activity",
        retry_state=RetryState.MAXIMUM_ATTEMPTS_REACHED,
    )
    error.__cause__ = cause
    return error


@pytest.fixture
def workflow_input() -> WizardRunActivityInput:
    return WizardRunActivityInput(team_id=1, run_id=uuid4())


@pytest.mark.asyncio
async def test_cloud_workflow_completes_after_worker_execution(
    monkeypatch: pytest.MonkeyPatch,
    workflow_input: WizardRunActivityInput,
) -> None:
    execute_activity = AsyncMock(side_effect=[None, None, None])
    monkeypatch.setattr(execute_run_workflow_module.workflow, "execute_activity", execute_activity)

    await ExecuteWizardRunWorkflow().run(workflow_input)

    assert [call.args[0] for call in execute_activity.await_args_list] == [start_run, execute_cloud_run, complete_run]
    assert all(call.args[1] == workflow_input for call in execute_activity.await_args_list)
    assert execute_activity.await_args_list[0].kwargs["retry_policy"].maximum_attempts == 3
    assert execute_activity.await_args_list[1].kwargs["retry_policy"].maximum_attempts == 1
    assert execute_activity.await_args_list[2].kwargs["retry_policy"].maximum_attempts == 3


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
    cause: BaseException,
    expected_error_code: WizardRunErrorCode,
) -> None:
    activity_error = _activity_error(cause)
    execute_activity = AsyncMock(side_effect=[None, activity_error, None])
    monkeypatch.setattr(execute_run_workflow_module.workflow, "execute_activity", execute_activity)

    with pytest.raises(ActivityError) as raised:
        await ExecuteWizardRunWorkflow().run(workflow_input)

    assert raised.value is activity_error
    assert execute_activity.await_args_list[2].args == (
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
) -> None:
    execute_activity = AsyncMock(side_effect=[None, asyncio.CancelledError(), None])
    monkeypatch.setattr(execute_run_workflow_module.workflow, "execute_activity", execute_activity)

    with pytest.raises(asyncio.CancelledError):
        await ExecuteWizardRunWorkflow().run(workflow_input)

    assert execute_activity.await_args_list[2].args == (cancel_run, workflow_input)


def test_cloud_workflow_identity_and_input_parsing() -> None:
    run_id = uuid4()

    assert ExecuteWizardRunWorkflow.workflow_id_for(run_id) == f"wizard-run-{run_id}"
    assert ExecuteWizardRunWorkflow.parse_inputs([f'{{"team_id": 1, "run_id": "{run_id}"}}']) == WizardRunActivityInput(
        team_id=1,
        run_id=UUID(str(run_id)),
    )
