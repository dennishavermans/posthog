"""
Exported enums for wizard.

If an enum appears in a contract dataclass field, it belongs here.
Internal-only constants (DB magic values, feature flags) stay in
the implementation (logic.py, models.py).
"""

from enum import StrEnum


class WizardSessionRunPhase(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class WizardSessionTaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

    # These are not currently used, but we want to reserve them for future use.
    FAILED = "failed"
    CANCELED = "canceled"


class WizardRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WizardRunEnvironment(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class WizardWorkspaceType(StrEnum):
    LOCAL_FOLDER = "local_folder"
    GIT_REPOSITORY = "git_repository"


class WizardRunErrorCode(StrEnum):
    TIMEOUT = "timeout"
    EXECUTION_FAILED = "execution_failed"
    DISPATCH_FAILED = "dispatch_failed"


class WizardRunArtifactType(StrEnum):
    GIT_DIFF = "git_diff"
    PULL_REQUEST = "pull_request"
