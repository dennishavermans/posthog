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


# Errors


class IllegalStatusTransitionError(Exception):
    pass


# Inputs

# Outputs

# DTOs
