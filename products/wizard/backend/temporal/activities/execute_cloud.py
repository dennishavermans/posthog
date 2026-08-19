from temporalio import activity
from temporalio.exceptions import ApplicationError

from posthog.temporal.common.utils import asyncify

from products.tasks.backend.facade import repo_selection
from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import GitRepositoryWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.logic import cloud_worker
from products.wizard.backend.logic.cloud_worker import (
    WizardWorkerExecutionError,
    WizardWorkerInput,
    WizardWorkerTimeoutError,
)
from products.wizard.backend.temporal.contracts import WizardRunActivityInput

WIZARD_REPOSITORY_ACCESS_ERROR_TYPE = "WizardRepositoryAccessError"
WIZARD_RUN_CONFIGURATION_ERROR_TYPE = "WizardRunConfigurationError"
WIZARD_WORKER_EXECUTION_ERROR_TYPE = "WizardWorkerExecutionError"
WIZARD_WORKER_TIMEOUT_ERROR_TYPE = "WizardWorkerTimeoutError"


@activity.defn
@asyncify
def execute_cloud_run(input: WizardRunActivityInput) -> None:
    run = wizard_facade.get_run(input.team_id, input.run_id)
    if run.environment != WizardRunEnvironment.CLOUD or not isinstance(run.workspace, GitRepositoryWorkspace):
        raise ApplicationError(
            "Wizard run does not have a cloud Git repository workspace.",
            type=WIZARD_RUN_CONFIGURATION_ERROR_TYPE,
            non_retryable=True,
        )
    if run.created_by_id is None:
        raise ApplicationError(
            "Wizard run creator is no longer available.",
            type=WIZARD_RUN_CONFIGURATION_ERROR_TYPE,
            non_retryable=True,
        )

    integration_id = repo_selection.resolve_team_github_integration_id(input.team_id)
    if integration_id is None or not repo_selection.repository_accessible_via_integration(
        input.team_id,
        integration_id,
        run.workspace.repository,
    ):
        raise ApplicationError(
            "GitHub access to the Wizard run repository is unavailable.",
            type=WIZARD_REPOSITORY_ACCESS_ERROR_TYPE,
            non_retryable=True,
        )

    try:
        diff = cloud_worker.execute_wizard_worker(
            WizardWorkerInput(
                team_id=input.team_id,
                created_by_id=run.created_by_id,
                run_id=input.run_id,
                github_integration_id=integration_id,
                repository=run.workspace.repository,
            )
        )
    except WizardWorkerTimeoutError as error:
        raise ApplicationError(
            "Wizard Worker timed out.",
            type=WIZARD_WORKER_TIMEOUT_ERROR_TYPE,
            non_retryable=True,
        ) from error
    except WizardWorkerExecutionError as error:
        raise ApplicationError(
            "Wizard Worker execution failed.",
            type=WIZARD_WORKER_EXECUTION_ERROR_TYPE,
            non_retryable=True,
        ) from error

    wizard_facade.create_git_diff_artifact(input.team_id, input.run_id, diff)
