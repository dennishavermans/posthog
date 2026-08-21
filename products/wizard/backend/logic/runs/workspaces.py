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


def deserialize_workspace(workspace_type: str, metadata: object) -> WizardWorkspace:
    match WizardWorkspaceType(workspace_type):
        case WizardWorkspaceType.LOCAL_FOLDER:
            return LocalFolderWorkspace.from_dict(metadata)
        case WizardWorkspaceType.GIT_REPOSITORY:
            return GitRepositoryWorkspace.from_dict(metadata)
    raise ValueError("Unsupported Wizard workspace type")
