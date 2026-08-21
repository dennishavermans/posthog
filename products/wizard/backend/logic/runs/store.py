from uuid import UUID

from products.wizard.backend.facade.contracts import (
    ListWizardRunsInput,
    WizardProgram,
    WizardRunDTO,
    WizardRunPage,
    WizardWorkspace,
)
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import WizardRunNotFoundError
from products.wizard.backend.logic.programs import program_to_mapping
from products.wizard.backend.logic.runs.mappers import run_from_record, workspace_to_record
from products.wizard.backend.models import WizardRun


def _get_run_record(team_id: int, run_id: UUID, *, lock: bool = False) -> WizardRun:
    runs = WizardRun.objects.for_team(team_id)
    if lock:
        runs = runs.select_for_update()

    run = runs.filter(id=run_id).first()
    if run is None:
        raise WizardRunNotFoundError

    return run


def create_run(
    *,
    team_id: int,
    created_by_id: int,
    environment: WizardRunEnvironment,
    workspace: WizardWorkspace,
    program: WizardProgram,
    status: WizardRunStatus,
) -> WizardRunDTO:
    workspace_type, workspace_metadata = workspace_to_record(workspace)
    run = WizardRun.objects.for_team(team_id).create(
        team_id=team_id,
        created_by_id=created_by_id,
        environment=environment.value,
        workspace_type=workspace_type.value,
        workspace=workspace_metadata,
        program=program_to_mapping(program),
        status=status.value,
    )
    return run_from_record(run)


def get_run(team_id: int, run_id: UUID, *, lock: bool = False) -> WizardRunDTO:
    return run_from_record(_get_run_record(team_id, run_id, lock=lock))


def list_runs(params: ListWizardRunsInput) -> WizardRunPage:
    runs = WizardRun.objects.for_team(params.team_id).order_by("-created_at")
    page = runs[params.offset : params.offset + params.limit]
    return WizardRunPage(results=tuple(run_from_record(run) for run in page), count=runs.count())


def set_run_status(
    team_id: int,
    run_id: UUID,
    status: WizardRunStatus,
    error_code: WizardRunErrorCode | None,
) -> WizardRunDTO:
    run = _get_run_record(team_id, run_id)
    run.status = status.value
    run.error_code = error_code.value if error_code is not None else None
    run.save(update_fields=["status", "error_code", "updated_at"])
    return run_from_record(run)
