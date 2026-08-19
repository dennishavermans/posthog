from products.tasks.backend.facade import repo_selection
from products.wizard.backend.facade.runs import (
    CreateWizardRunInput,
    IllegalStatusTransitionError,
    InvalidTransitionMetadataError,
    MissingErrorCodeError,
    MissingGithubIntegrationError,
    MissingOutcomeError,
    MissingRepositoryError,
    RepositoryNotAccessibleError,
    WizardRunDTO,
    WizardRunErrorCode,
    WizardRunOutcome,
    WizardRunStatus,
    WizardRunSurface,
)
from products.wizard.backend.models import WizardRun

_ALLOWED_STATUS_TRANSITIONS = {
    (WizardRunStatus.QUEUED, WizardRunStatus.RUNNING),
    (WizardRunStatus.QUEUED, WizardRunStatus.FAILED),
    (WizardRunStatus.QUEUED, WizardRunStatus.CANCELLED),
    (WizardRunStatus.RUNNING, WizardRunStatus.COMPLETED),
    (WizardRunStatus.RUNNING, WizardRunStatus.FAILED),
    (WizardRunStatus.RUNNING, WizardRunStatus.CANCELLED),
}


def transition(
    current_status: WizardRunStatus,
    next_status: WizardRunStatus,
    *,
    outcome: WizardRunOutcome | None = None,
    error_code: WizardRunErrorCode | None = None,
) -> WizardRunStatus:
    if (current_status, next_status) not in _ALLOWED_STATUS_TRANSITIONS:
        raise IllegalStatusTransitionError

    # These prevent passing an outcome or error code when the next status doesn't require it

    if outcome is not None and next_status != WizardRunStatus.COMPLETED:
        raise InvalidTransitionMetadataError

    if error_code is not None and next_status != WizardRunStatus.FAILED:
        raise InvalidTransitionMetadataError

    # These enforce that an outcome or error code is provided when the next status requires it

    if next_status == WizardRunStatus.COMPLETED and outcome is None:
        raise MissingOutcomeError

    if next_status == WizardRunStatus.FAILED and error_code is None:
        raise MissingErrorCodeError

    return next_status


def create_run(params: CreateWizardRunInput) -> WizardRunDTO:
    if params.surface == WizardRunSurface.CLOUD:
        if params.repository is None:
            raise MissingRepositoryError

        integration = repo_selection.resolve_team_github_integration(params.team_id, team_only=True)

        if integration is None:
            raise MissingGithubIntegrationError

        if not repo_selection.repository_accessible_via_integration(
            params.team_id, integration.integration.id, params.repository
        ):
            raise RepositoryNotAccessibleError

    created = WizardRun.objects.create(
        team_id=params.team_id,
        created_by_id=params.created_by_id,
        surface=params.surface.value,
        status=WizardRunStatus.QUEUED.value,
    )

    return _to_dto(created)


def _to_dto(run: WizardRun) -> WizardRunDTO:
    return WizardRunDTO(
        id=run.id,
        team_id=run.team_id,
        created_by_id=run.created_by_id,
        surface=WizardRunSurface(run.surface),
        status=WizardRunStatus(run.status),
        outcome=WizardRunOutcome(run.outcome) if run.outcome else None,
        error_code=WizardRunErrorCode(run.error_code) if run.error_code else None,
    )
