import json
import asyncio
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, TimeoutError

from posthog.temporal.common.base import PostHogWorkflow

from products.wizard.backend.facade.enums import WizardRunErrorCode
from products.wizard.backend.temporal.activities.execute_cloud import (
    WIZARD_WORKER_TIMEOUT_ERROR_TYPE,
    execute_cloud_run,
)
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.constants import EXECUTE_WIZARD_RUN_WORKFLOW, wizard_run_workflow_id
from products.wizard.backend.temporal.contracts import WizardRunActivityInput, WizardRunFailureActivityInput

LIFECYCLE_TIMEOUT = timedelta(minutes=1)
WORKER_TIMEOUT = timedelta(minutes=50)
LIFECYCLE_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
WORKER_RETRY_POLICY = RetryPolicy(maximum_attempts=1)


@workflow.defn(name=EXECUTE_WIZARD_RUN_WORKFLOW)
class ExecuteWizardRunWorkflow(PostHogWorkflow):
    @staticmethod
    def workflow_id_for(run_id: UUID) -> str:
        return wizard_run_workflow_id(run_id)

    @staticmethod
    def parse_inputs(inputs: list[str]) -> WizardRunActivityInput:
        loaded = json.loads(inputs[0])
        return WizardRunActivityInput(team_id=loaded["team_id"], run_id=UUID(loaded["run_id"]))

    @workflow.run
    async def run(self, input: WizardRunActivityInput) -> None:
        try:
            await self._run(input)
        except asyncio.CancelledError:
            await workflow.execute_activity(
                cancel_run,
                input,
                start_to_close_timeout=LIFECYCLE_TIMEOUT,
                retry_policy=LIFECYCLE_RETRY_POLICY,
            )
            raise

    async def _run(self, input: WizardRunActivityInput) -> None:
        await workflow.execute_activity(
            start_run,
            input,
            start_to_close_timeout=LIFECYCLE_TIMEOUT,
            retry_policy=LIFECYCLE_RETRY_POLICY,
        )

        try:
            await workflow.execute_activity(
                execute_cloud_run,
                input,
                start_to_close_timeout=WORKER_TIMEOUT,
                retry_policy=WORKER_RETRY_POLICY,
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
            await workflow.execute_activity(
                complete_run,
                input,
                start_to_close_timeout=LIFECYCLE_TIMEOUT,
                retry_policy=LIFECYCLE_RETRY_POLICY,
            )
        except ActivityError as error:
            await workflow.execute_activity(
                fail_run,
                WizardRunFailureActivityInput(
                    team_id=input.team_id,
                    run_id=input.run_id,
                    error_code=self._error_code_for(error),
                ),
                start_to_close_timeout=LIFECYCLE_TIMEOUT,
                retry_policy=LIFECYCLE_RETRY_POLICY,
            )
            raise

    @staticmethod
    def _error_code_for(error: ActivityError) -> WizardRunErrorCode:
        cause = error.cause
        if isinstance(cause, TimeoutError):
            return WizardRunErrorCode.TIMEOUT
        if isinstance(cause, ApplicationError) and cause.type == WIZARD_WORKER_TIMEOUT_ERROR_TYPE:
            return WizardRunErrorCode.TIMEOUT
        return WizardRunErrorCode.EXECUTION_FAILED
