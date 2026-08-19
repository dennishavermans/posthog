# Enums


from enum import StrEnum
from uuid import UUID

from posthog.dataclasses import frozen


class WizardRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WizardRunSurface(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class WizardRunOutcome(StrEnum):
    CHANGES_CREATED = "changes_created"


# Errors


class MissingOutcomeError(Exception):
    pass


class MissingGithubIntegrationError(Exception):
    pass


class MissingRepositoryError(Exception):
    pass


class RepositoryNotAccessibleError(Exception):
    pass


class IllegalStatusTransitionError(Exception):
    pass


class WizardRunErrorCode(StrEnum):
    TIMEOUT = "timeout"


class MissingErrorCodeError(Exception):
    pass


class InvalidTransitionMetadataError(Exception):
    pass


# Inputs


@frozen
class LocalWizardRunTarget:
    project_name: str


@frozen
class CloudWizardRunTarget:
    repository: str
    ref: str | None = None


type WizardRunTarget = LocalWizardRunTarget | CloudWizardRunTarget


@frozen
class CreateWizardRunInput:
    team_id: int
    created_by_id: int
    surface: WizardRunSurface
    repository: str | None = None


# DTOs


@frozen
class WizardRunDTO:
    id: UUID
    team_id: int
    created_by_id: int
    surface: WizardRunSurface
    status: WizardRunStatus
    outcome: WizardRunOutcome | None
    error_code: WizardRunErrorCode | None
