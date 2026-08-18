from products.wizard.backend.facade.runs import (
    IllegalStatusTransitionError,
    InvalidTransitionMetadataError,
    MissingErrorCodeError,
    MissingOutcomeError,
    WizardRunErrorCode,
    WizardRunOutcome,
    WizardRunStatus,
)

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
