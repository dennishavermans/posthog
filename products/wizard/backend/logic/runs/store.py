from uuid import UUID

from products.wizard.backend.facade.contracts import WizardRunDTO
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import WizardRunNotFoundError
from products.wizard.backend.logic import registry as registry_service
from products.wizard.backend.logic.runs.workspaces import deserialize_workspace
from products.wizard.backend.models import WizardRun


def get_run_model(team_id: int, run_id: UUID, *, lock: bool = False) -> WizardRun:
    runs = WizardRun.objects.for_team(team_id)
    if lock:
        runs = runs.select_for_update()

    run = runs.filter(id=run_id).first()
    if run is None:
        raise WizardRunNotFoundError

    return run


def to_dto(run: WizardRun) -> WizardRunDTO:
    return WizardRunDTO(
        id=run.id,
        team_id=run.team_id,
        created_by_id=run.created_by_id,
        environment=WizardRunEnvironment(run.environment),
        workspace=deserialize_workspace(run.workspace_type, run.workspace),
        program=registry_service.deserialize_program(run.program),
        status=WizardRunStatus(run.status),
        error_code=WizardRunErrorCode(run.error_code) if run.error_code else None,
    )
