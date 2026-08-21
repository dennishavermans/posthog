from temporalio.exceptions import ActivityError, ApplicationError, TimeoutError

from products.wizard.backend.facade.enums import WizardRunErrorCode
from products.wizard.backend.temporal.activities.errors import WIZARD_WORKER_TIMEOUT_ERROR_TYPE


def wizard_run_error_code(error: ActivityError) -> WizardRunErrorCode:
    cause = error.cause
    if isinstance(cause, TimeoutError):
        return WizardRunErrorCode.TIMEOUT
    if isinstance(cause, ApplicationError) and cause.type == WIZARD_WORKER_TIMEOUT_ERROR_TYPE:
        return WizardRunErrorCode.TIMEOUT
    return WizardRunErrorCode.EXECUTION_FAILED
