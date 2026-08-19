from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import (
    IllegalStatusTransitionError,
    InvalidRepositoryError,
    InvalidTransitionMetadataError,
    InvalidWorkspaceEnvironmentError,
)

_ALLOWED_STATUS_TRANSITIONS = {
    (WizardRunStatus.CREATED, WizardRunStatus.RUNNING),
    (WizardRunStatus.CREATED, WizardRunStatus.FAILED),
    (WizardRunStatus.CREATED, WizardRunStatus.CANCELLED),
    (WizardRunStatus.RUNNING, WizardRunStatus.COMPLETED),
    (WizardRunStatus.RUNNING, WizardRunStatus.FAILED),
    (WizardRunStatus.RUNNING, WizardRunStatus.CANCELLED),
}


def transition(
    current_status: WizardRunStatus,
    next_status: WizardRunStatus,
    *,
    error_code: WizardRunErrorCode | None = None,
) -> WizardRunStatus:
    if (current_status, next_status) not in _ALLOWED_STATUS_TRANSITIONS:
        raise IllegalStatusTransitionError

    if error_code is not None and next_status != WizardRunStatus.FAILED:
        raise InvalidTransitionMetadataError

    return next_status


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
