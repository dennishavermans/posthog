import json
import asyncio
from datetime import timedelta
from uuid import UUID

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, TimeoutError

from posthog.temporal.common.base import PostHogWorkflow

from products.wizard.backend.facade.enums import WizardRunErrorCode, WizardWorkspaceType
from products.wizard.backend.temporal.activities.errors import WIZARD_WORKER_TIMEOUT_ERROR_TYPE
from products.wizard.backend.temporal.activities.execution import execute_wizard
from products.wizard.backend.temporal.activities.handoff import create_run_artifacts
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.activities.workspace import clone_repository, destroy_worker, provision_worker
from products.wizard.backend.temporal.constants import EXECUTE_WIZARD_RUN_WORKFLOW, wizard_run_workflow_id
from products.wizard.backend.temporal.contracts import (
    PreparedGitRepositoryWorkspace,
    ProvisionedWizardWorker,
    WizardRunActivityInput,
    WizardRunFailureActivityInput,
)

LIFECYCLE_TIMEOUT = timedelta(minutes=1)
PROVISION_TIMEOUT = timedelta(minutes=5)
PREPARATION_TIMEOUT = timedelta(minutes=10)
EXECUTION_TIMEOUT = timedelta(minutes=50)
HANDOFF_TIMEOUT = timedelta(minutes=5)
CLEANUP_TIMEOUT = timedelta(minutes=5)
LIFECYCLE_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
WORKER_RETRY_POLICY = RetryPolicy(maximum_attempts=1)
CLEANUP_RETRY_POLICY = RetryPolicy(maximum_attempts=3)


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
            await self._execute(input)
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

    async def _execute(self, input: WizardRunActivityInput) -> None:
        worker = await workflow.execute_activity(
            provision_worker,
            input,
            start_to_close_timeout=PROVISION_TIMEOUT,
            retry_policy=WORKER_RETRY_POLICY,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )
        try:
            workspace = await self._prepare_workspace(worker)
            await workflow.execute_activity(
                execute_wizard,
                workspace,
                start_to_close_timeout=EXECUTION_TIMEOUT,
                retry_policy=WORKER_RETRY_POLICY,
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
            await workflow.execute_activity(
                create_run_artifacts,
                workspace,
                start_to_close_timeout=HANDOFF_TIMEOUT,
                retry_policy=WORKER_RETRY_POLICY,
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
        finally:
            await workflow.execute_activity(
                destroy_worker,
                worker,
                start_to_close_timeout=CLEANUP_TIMEOUT,
                retry_policy=CLEANUP_RETRY_POLICY,
            )

    @staticmethod
    async def _prepare_workspace(worker: ProvisionedWizardWorker) -> PreparedGitRepositoryWorkspace:
        if worker.workspace_type == WizardWorkspaceType.GIT_REPOSITORY:
            return await workflow.execute_activity(
                clone_repository,
                worker,
                start_to_close_timeout=PREPARATION_TIMEOUT,
                retry_policy=WORKER_RETRY_POLICY,
                cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )
        raise ValueError(f"Unsupported cloud workspace type: {worker.workspace_type}")

    @staticmethod
    def _error_code_for(error: ActivityError) -> WizardRunErrorCode:
        cause = error.cause
        if isinstance(cause, TimeoutError):
            return WizardRunErrorCode.TIMEOUT
        if isinstance(cause, ApplicationError) and cause.type == WIZARD_WORKER_TIMEOUT_ERROR_TYPE:
            return WizardRunErrorCode.TIMEOUT
        return WizardRunErrorCode.EXECUTION_FAILED
