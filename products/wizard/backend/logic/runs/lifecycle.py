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
    WizardRunDTO,
    WizardRunPage,
)
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import (
    MissingGitHubIntegrationError,
    RepositoryNotAccessibleError,
    WizardProgramEnvironmentNotSupportedError,
)
from products.wizard.backend.logic import registry as registry_service
from products.wizard.backend.logic.runs.store import get_run_model, to_dto
from products.wizard.backend.logic.runs.transitions import transition
from products.wizard.backend.logic.runs.workspaces import (
    serialize_workspace,
    validate_git_repository,
    validate_workspace_environment,
)
from products.wizard.backend.models import WizardRun
from products.wizard.backend.temporal import client as temporal_client
from products.wizard.backend.temporal.contracts import WizardRunActivityInput

logger = logging.getLogger(__name__)


def create_run(params: CreateWizardRunInput) -> WizardRunDTO:
    validate_workspace_environment(params.environment, params.workspace)
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

    workspace_type, workspace_metadata = serialize_workspace(params.workspace)
    initial_status = (
        WizardRunStatus.RUNNING if params.environment == WizardRunEnvironment.LOCAL else WizardRunStatus.CREATED
    )

    with database_transaction.atomic():
        created = WizardRun.objects.for_team(params.team_id).create(
            team_id=params.team_id,
            created_by_id=params.created_by_id,
            environment=params.environment.value,
            workspace_type=workspace_type.value,
            workspace=workspace_metadata,
            program=program.to_dict(),
            status=initial_status.value,
        )
        if params.environment == WizardRunEnvironment.CLOUD:
            database_transaction.on_commit(
                partial(
                    _dispatch_cloud_run,
                    WizardRunActivityInput(team_id=params.team_id, run_id=created.id),
                )
            )

    if params.environment == WizardRunEnvironment.CLOUD:
        created.refresh_from_db(fields=["status", "error_code", "updated_at"])
    return to_dto(created)


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
    return to_dto(get_run_model(team_id, run_id))


def list_runs(params: ListWizardRunsInput) -> WizardRunPage:
    runs = WizardRun.objects.for_team(params.team_id).order_by("-created_at")
    page = runs[params.offset : params.offset + params.limit]
    return WizardRunPage(results=tuple(to_dto(run) for run in page), count=runs.count())


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
        run = get_run_model(team_id, run_id, lock=True)
        next_status = transition(WizardRunStatus(run.status), next_status, error_code=error_code)
        run.status = next_status.value
        run.error_code = error_code.value if error_code is not None else None
        run.save(update_fields=["status", "error_code", "updated_at"])

    return to_dto(run)
