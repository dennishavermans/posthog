import logging
from functools import partial
from uuid import UUID

from django.db import transaction as database_transaction

from posthog.models import Team, User

from products.tasks.backend.facade import repo_selection
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    ListWizardRunsInput,
    LocalFolderWorkspace,
    WizardRunDTO,
    WizardRunPage,
)
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import (
    InvalidWorkspaceEnvironmentError,
    MissingGitHubIntegrationError,
    RepositoryNotAccessibleError,
    WizardProgramEnvironmentNotSupportedError,
)
from products.wizard.backend.logic import registry as registry_service
from products.wizard.backend.logic.runs import store
from products.wizard.backend.logic.runs.transitions import transition
from products.wizard.backend.logic.runs.validation import validate_git_repository
from products.wizard.backend.temporal import client as temporal_client
from products.wizard.backend.temporal.contracts import WizardRunActivityInput

logger = logging.getLogger(__name__)


def create_run(params: CreateWizardRunInput) -> WizardRunDTO:
    match params.environment, params.workspace:
        case WizardRunEnvironment.LOCAL, LocalFolderWorkspace():
            pass
        case WizardRunEnvironment.CLOUD, GitRepositoryWorkspace():
            pass
        case _:
            raise InvalidWorkspaceEnvironmentError

    user = User.objects.only("distinct_id").get(id=params.created_by_id)
    team = Team.objects.only("organization_id").get(id=params.team_id)

    program = registry_service.get_program(
        program_id=params.program_id,
        distinct_id=user.distinct_id,
        organization_id=str(team.organization_id),
    )

    if params.environment not in program.supported_environments:
        raise WizardProgramEnvironmentNotSupportedError

    if isinstance(params.workspace, GitRepositoryWorkspace):
        validate_git_repository(params.workspace.repository)

        integration_id = repo_selection.resolve_team_github_integration_id(params.team_id)

        if integration_id is None:
            raise MissingGitHubIntegrationError

        if not repo_selection.repository_accessible_via_integration(
            params.team_id,
            integration_id,
            params.workspace.repository,
        ):
            raise RepositoryNotAccessibleError

    initial_status = (
        WizardRunStatus.RUNNING if params.environment == WizardRunEnvironment.LOCAL else WizardRunStatus.CREATED
    )

    with database_transaction.atomic():
        created = store.create_run(
            team_id=params.team_id,
            created_by_id=params.created_by_id,
            environment=params.environment,
            workspace=params.workspace,
            program=program,
            status=initial_status,
        )

        if params.environment == WizardRunEnvironment.CLOUD:
            database_transaction.on_commit(
                partial(
                    _dispatch_cloud_run,
                    WizardRunActivityInput(team_id=params.team_id, run_id=created.id),
                )
            )

    if params.environment == WizardRunEnvironment.CLOUD:
        return store.get_run(params.team_id, created.id)
    return created


def _dispatch_cloud_run(input: WizardRunActivityInput) -> None:
    try:
        temporal_client.start_wizard_run_workflow(input)
    except Exception:
        logger.exception(
            "wizard_run_dispatch_failed",
            extra={"team_id": input.team_id, "run_id": str(input.run_id)},
        )
        fail_run(input.team_id, input.run_id, error_code=WizardRunErrorCode.DISPATCH_FAILED)


def get_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return store.get_run(team_id, run_id)


def list_runs(params: ListWizardRunsInput) -> WizardRunPage:
    return store.list_runs(params)


def start_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return transition_run(team_id, run_id, WizardRunStatus.RUNNING)


def complete_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return transition_run(team_id, run_id, WizardRunStatus.COMPLETED)


def fail_run(
    team_id: int,
    run_id: UUID,
    *,
    error_code: WizardRunErrorCode | None = None,
) -> WizardRunDTO:
    return transition_run(team_id, run_id, WizardRunStatus.FAILED, error_code=error_code)


def cancel_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    return transition_run(team_id, run_id, WizardRunStatus.CANCELLED)


def transition_run(
    team_id: int,
    run_id: UUID,
    next_status: WizardRunStatus,
    *,
    error_code: WizardRunErrorCode | None = None,
) -> WizardRunDTO:
    with database_transaction.atomic():
        run = store.get_run(team_id, run_id, lock=True)
        next_status = transition(run.status, next_status, error_code=error_code)
        run = store.set_run_status(team_id, run_id, next_status, error_code)

    return run
