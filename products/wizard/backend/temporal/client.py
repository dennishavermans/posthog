from datetime import timedelta

from django.conf import settings

from asgiref.sync import async_to_sync
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from posthog.temporal.common.client import async_connect

from products.wizard.backend.temporal.constants import EXECUTE_WIZARD_RUN_WORKFLOW, wizard_run_workflow_id
from products.wizard.backend.temporal.contracts import WizardRunActivityInput

WORKFLOW_RETRY_POLICY = RetryPolicy(maximum_attempts=1)
WORKFLOW_EXECUTION_TIMEOUT = timedelta(minutes=60)


@async_to_sync
async def start_wizard_run_workflow(input: WizardRunActivityInput) -> None:
    client = await async_connect()
    try:
        await client.start_workflow(
            EXECUTE_WIZARD_RUN_WORKFLOW,
            input,
            id=wizard_run_workflow_id(input.run_id),
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            task_queue=settings.TASKS_TASK_QUEUE,
            retry_policy=WORKFLOW_RETRY_POLICY,
            execution_timeout=WORKFLOW_EXECUTION_TIMEOUT,
        )
    except WorkflowAlreadyStartedError:
        return
