from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardWorkspaceType
from products.wizard.backend.facade.errors import InvalidRepositoryError, InvalidWorkspaceEnvironmentError


def validate_workspace_environment(environment: WizardRunEnvironment, workspace: WizardWorkspace) -> None:
    match environment, workspace:
        case WizardRunEnvironment.LOCAL, LocalFolderWorkspace():
            return
        case WizardRunEnvironment.CLOUD, GitRepositoryWorkspace():
            return
        case _:
            raise InvalidWorkspaceEnvironmentError


def validate_git_repository(repository: str) -> None:
    owner, separator, name = repository.partition("/")
    if not separator or not owner or not name or "/" in name:
        raise InvalidRepositoryError


def serialize_workspace(workspace: WizardWorkspace) -> tuple[WizardWorkspaceType, dict[str, str]]:
    match workspace:
        case LocalFolderWorkspace(project_name=project_name):
            return WizardWorkspaceType.LOCAL_FOLDER, {"project_name": project_name}
        case GitRepositoryWorkspace(repository=repository):
            return WizardWorkspaceType.GIT_REPOSITORY, {"repository": repository}
    raise ValueError("Unsupported Wizard workspace")


def deserialize_workspace(workspace_type: str, metadata: object) -> WizardWorkspace:
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
