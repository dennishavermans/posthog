from products.wizard.backend.facade.enums import WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.logic.runs.validation import validate_status_transition


def transition(
    current_status: WizardRunStatus,
    next_status: WizardRunStatus,
    *,
    error_code: WizardRunErrorCode | None = None,
) -> WizardRunStatus:
    validate_status_transition(current_status, next_status, error_code=error_code)
    return next_status
