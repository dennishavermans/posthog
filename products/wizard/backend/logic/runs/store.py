from uuid import UUID

from products.wizard.backend.facade.contracts import (
    ListWizardRunsInput,
    WizardProgram,
    WizardRunCreationResult,
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
    idempotency_key: str | None = None,
    request_fingerprint: str | None = None,
) -> WizardRunCreationResult:
    workspace_type, workspace_metadata = workspace_to_record(workspace)
    values = {
        "created_by_id": created_by_id,
        "environment": environment.value,
        "workspace_type": workspace_type.value,
        "workspace": workspace_metadata,
        "program": program_to_mapping(program),
        "status": status.value,
        "request_fingerprint": request_fingerprint,
    }
    if idempotency_key is None:
        run = WizardRun.objects.for_team(team_id).create(team_id=team_id, idempotency_key=None, **values)
        return WizardRunCreationResult(run=run_from_record(run), created=True)

    run, created = WizardRun.objects.for_team(team_id).get_or_create(
        team_id=team_id,
        idempotency_key=idempotency_key,
        defaults=values,
    )
    return WizardRunCreationResult(run=run_from_record(run), created=created)


def get_run_by_idempotency_key(team_id: int, idempotency_key: str) -> WizardRunDTO | None:
    run = WizardRun.objects.for_team(team_id).filter(idempotency_key=idempotency_key).first()
    return run_from_record(run) if run is not None else None


def get_request_fingerprint(team_id: int, run_id: UUID) -> str | None:
    return _get_run_record(team_id, run_id).request_fingerprint


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
