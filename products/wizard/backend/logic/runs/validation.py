from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import (
    IllegalStatusTransitionError,
    InvalidRepositoryError,
    InvalidTransitionMetadataError,
    InvalidWorkspaceEnvironmentError,
)

_ALLOWED_STATUS_TRANSITIONS = frozenset(
    {
        (WizardRunStatus.CREATED, WizardRunStatus.RUNNING),
        (WizardRunStatus.CREATED, WizardRunStatus.FAILED),
        (WizardRunStatus.CREATED, WizardRunStatus.CANCELLED),
        (WizardRunStatus.RUNNING, WizardRunStatus.COMPLETED),
        (WizardRunStatus.RUNNING, WizardRunStatus.FAILED),
        (WizardRunStatus.RUNNING, WizardRunStatus.CANCELLED),
    }
)


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


def validate_status_transition(
    current_status: WizardRunStatus,
    next_status: WizardRunStatus,
    *,
    error_code: WizardRunErrorCode | None = None,
) -> None:
    if (current_status, next_status) not in _ALLOWED_STATUS_TRANSITIONS:
        raise IllegalStatusTransitionError
    if error_code is not None and next_status != WizardRunStatus.FAILED:
        raise InvalidTransitionMetadataError


def validate_git_diff_artifact_metadata(size_bytes: int | None, content_hash: str | None) -> None:
    if size_bytes is None or content_hash is None:
        raise ValueError("Git diff artifact is missing stored content metadata.")


def validate_pull_request_artifact_metadata(
    url: str | None, number: object, repository: object, head_branch: object, base_branch: object
) -> None:
    if (
        url is None
        or not isinstance(number, int)
        or not isinstance(repository, str)
        or not isinstance(head_branch, str)
        or not isinstance(base_branch, str)
    ):
        raise ValueError("Pull request artifact is missing repository metadata.")
