from collections.abc import Callable

from temporalio import activity

from posthog.temporal.common.utils import asyncify

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import WizardRunDTO
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import IllegalStatusTransitionError
from products.wizard.backend.temporal.contracts import WizardRunActivityInput, WizardRunFailureActivityInput


@activity.defn(name="wizard_start_run")
@asyncify
def start_run(input: WizardRunActivityInput) -> None:
    _transition(
        input,
        expected_status=WizardRunStatus.RUNNING,
        expected_error_code=None,
        operation=lambda: wizard_facade.start_run(input.team_id, input.run_id),
    )


@activity.defn(name="wizard_complete_run")
@asyncify
def complete_run(input: WizardRunActivityInput) -> None:
    _transition(
        input,
        expected_status=WizardRunStatus.COMPLETED,
        expected_error_code=None,
        operation=lambda: wizard_facade.complete_run(input.team_id, input.run_id),
    )


@activity.defn(name="wizard_fail_run")
@asyncify
def fail_run(input: WizardRunFailureActivityInput) -> None:
    _transition(
        input,
        expected_status=WizardRunStatus.FAILED,
        expected_error_code=input.error_code,
        operation=lambda: wizard_facade.fail_run(input.team_id, input.run_id, error_code=input.error_code),
    )


@activity.defn(name="wizard_cancel_run")
@asyncify
def cancel_run(input: WizardRunActivityInput) -> None:
    _transition(
        input,
        expected_status=WizardRunStatus.CANCELLED,
        expected_error_code=None,
        operation=lambda: wizard_facade.cancel_run(input.team_id, input.run_id),
    )


def _transition(
    input: WizardRunActivityInput | WizardRunFailureActivityInput,
    *,
    expected_status: WizardRunStatus,
    expected_error_code: WizardRunErrorCode | None,
    operation: Callable[[], WizardRunDTO],
) -> None:
    current = _get_cloud_run(input)
    if _matches(current, expected_status, expected_error_code):
        return

    try:
        operation()
    except IllegalStatusTransitionError:
        current = _get_cloud_run(input)
        if _matches(current, expected_status, expected_error_code):
            return
        raise


def _get_cloud_run(input: WizardRunActivityInput | WizardRunFailureActivityInput) -> WizardRunDTO:
    run = wizard_facade.get_run(input.team_id, input.run_id)
    if run.environment != WizardRunEnvironment.CLOUD:
        raise ValueError("Lifecycle activity requires a cloud Wizard run.")
    return run


def _matches(
    run: WizardRunDTO,
    status: WizardRunStatus,
    error_code: WizardRunErrorCode | None,
) -> bool:
    return run.status == status and run.error_code == error_code
