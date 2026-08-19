from uuid import UUID

from products.tasks.backend.facade import repo_selection
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    LocalFolderWorkspace,
    WizardRunDTO,
    WizardWorkspace,
)
from products.wizard.backend.facade.enums import (
    WizardRunEnvironment,
    WizardRunErrorCode,
    WizardRunStatus,
    WizardWorkspaceType,
)
from products.wizard.backend.facade.errors import (
    MissingGitHubIntegrationError,
    RepositoryNotAccessibleError,
    WizardRunNotFoundError,
)
from products.wizard.backend.logic.run_domain import validate_workspace_environment
from products.wizard.backend.models import WizardRun


def create_run(params: CreateWizardRunInput) -> WizardRunDTO:
    validate_workspace_environment(params.environment, params.workspace)

    if isinstance(params.workspace, GitRepositoryWorkspace):
        integration_id = repo_selection.resolve_team_github_integration_id(params.team_id)
        if integration_id is None:
            raise MissingGitHubIntegrationError
        if not repo_selection.repository_accessible_via_integration(
            params.team_id,
            integration_id,
            params.workspace.repository,
        ):
            raise RepositoryNotAccessibleError

    workspace_type, workspace_metadata = _serialize_workspace(params.workspace)
    initial_status = (
        WizardRunStatus.RUNNING if params.environment == WizardRunEnvironment.LOCAL else WizardRunStatus.CREATED
    )

    created = WizardRun.objects.create(
        team_id=params.team_id,
        created_by_id=params.created_by_id,
        environment=params.environment.value,
        workspace_type=workspace_type.value,
        workspace=workspace_metadata,
        status=initial_status.value,
    )

    return _to_dto(created)


def get_run(team_id: int, run_id: UUID) -> WizardRunDTO:
    run = WizardRun.objects.for_team(team_id).filter(id=run_id).first()
    if run is None:
        raise WizardRunNotFoundError

    return _to_dto(run)


def _to_dto(run: WizardRun) -> WizardRunDTO:
    return WizardRunDTO(
        id=run.id,
        team_id=run.team_id,
        created_by_id=run.created_by_id,
        environment=WizardRunEnvironment(run.environment),
        workspace=_deserialize_workspace(run.workspace_type, run.workspace),
        status=WizardRunStatus(run.status),
        error_code=WizardRunErrorCode(run.error_code) if run.error_code else None,
    )


def _serialize_workspace(workspace: WizardWorkspace) -> tuple[WizardWorkspaceType, dict[str, str]]:
    match workspace:
        case LocalFolderWorkspace(project_name=project_name):
            return WizardWorkspaceType.LOCAL_FOLDER, {"project_name": project_name}
        case GitRepositoryWorkspace(repository=repository):
            return WizardWorkspaceType.GIT_REPOSITORY, {"repository": repository}
    raise ValueError("Unsupported Wizard workspace")


def _deserialize_workspace(workspace_type: str, metadata: object) -> WizardWorkspace:
    match WizardWorkspaceType(workspace_type):
        case WizardWorkspaceType.LOCAL_FOLDER:
            return LocalFolderWorkspace(project_name=_workspace_metadata_value(metadata, "project_name"))
        case WizardWorkspaceType.GIT_REPOSITORY:
            return GitRepositoryWorkspace(repository=_workspace_metadata_value(metadata, "repository"))
    raise ValueError("Unsupported Wizard workspace type")


def _workspace_metadata_value(metadata: object, key: str) -> str:
    if not isinstance(metadata, dict):
        raise ValueError("Wizard workspace metadata must be an object")

    value: object = metadata.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Wizard workspace metadata field {key!r} must be a string")

    return value
