from enum import StrEnum

# Enums


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


class IllegalStatusTransitionError(Exception):
    pass


class WizardRunErrorCode(StrEnum):
    TIMEOUT = "timeout"


class MissingErrorCodeError(Exception):
    pass


class InvalidTransitionMetadataError(Exception):
    pass


# Inputs

# Outputs

# DTOs
