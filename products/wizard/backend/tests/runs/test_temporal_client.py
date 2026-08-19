from types import SimpleNamespace
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock

from django.conf import settings

from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from products.wizard.backend.temporal import client as temporal_client
from products.wizard.backend.temporal.contracts import WizardRunActivityInput
from products.wizard.backend.temporal.workflows.execute_run import ExecuteWizardRunWorkflow


def test_start_wizard_run_workflow_uses_stable_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    start_workflow = AsyncMock()
    connect = AsyncMock(return_value=SimpleNamespace(start_workflow=start_workflow))
    monkeypatch.setattr(temporal_client, "async_connect", connect)
    input = WizardRunActivityInput(team_id=1, run_id=uuid4())

    temporal_client.start_wizard_run_workflow(input)

    start_workflow.assert_awaited_once_with(
        ExecuteWizardRunWorkflow.get_name(),
        input,
        id=ExecuteWizardRunWorkflow.workflow_id_for(input.run_id),
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        task_queue=settings.TASKS_TASK_QUEUE,
        retry_policy=temporal_client.WORKFLOW_RETRY_POLICY,
        execution_timeout=temporal_client.WORKFLOW_EXECUTION_TIMEOUT,
    )


def test_start_wizard_run_workflow_accepts_duplicate_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    input = WizardRunActivityInput(team_id=1, run_id=uuid4())
    start_workflow = AsyncMock(
        side_effect=WorkflowAlreadyStartedError(
            ExecuteWizardRunWorkflow.workflow_id_for(input.run_id),
            ExecuteWizardRunWorkflow.get_name(),
        )
    )
    connect = AsyncMock(return_value=SimpleNamespace(start_workflow=start_workflow))
    monkeypatch.setattr(temporal_client, "async_connect", connect)

    temporal_client.start_wizard_run_workflow(input)
