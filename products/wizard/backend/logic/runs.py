from products.wizard.backend.facade.runs import IllegalStatusTransitionError, WizardRunStatus

_ALLOWED_STATUS_TRANSITIONS = {
    (WizardRunStatus.QUEUED, WizardRunStatus.RUNNING),
    (WizardRunStatus.QUEUED, WizardRunStatus.FAILED),
    (WizardRunStatus.QUEUED, WizardRunStatus.CANCELLED),
    (WizardRunStatus.RUNNING, WizardRunStatus.COMPLETED),
    (WizardRunStatus.RUNNING, WizardRunStatus.FAILED),
    (WizardRunStatus.RUNNING, WizardRunStatus.CANCELLED),
}


def transition(current_status: WizardRunStatus, next_status: WizardRunStatus) -> WizardRunStatus:
    if (current_status, next_status) not in _ALLOWED_STATUS_TRANSITIONS:
        raise IllegalStatusTransitionError

    return next_status
