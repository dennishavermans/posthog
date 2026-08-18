from itertools import product

import pytest

from products.wizard.backend.facade.runs import IllegalStatusTransitionError, WizardRunStatus
from products.wizard.backend.logic.runs import transition

ALLOWED_TRANSITIONS = (
    (WizardRunStatus.QUEUED, WizardRunStatus.RUNNING),
    (WizardRunStatus.QUEUED, WizardRunStatus.FAILED),
    (WizardRunStatus.QUEUED, WizardRunStatus.CANCELLED),
    (WizardRunStatus.RUNNING, WizardRunStatus.COMPLETED),
    (WizardRunStatus.RUNNING, WizardRunStatus.FAILED),
    (WizardRunStatus.RUNNING, WizardRunStatus.CANCELLED),
)

ILLEGAL_TRANSITIONS = tuple(
    transition for transition in product(WizardRunStatus, repeat=2) if transition not in ALLOWED_TRANSITIONS
)


@pytest.mark.parametrize("current_status, next_status", ALLOWED_TRANSITIONS)
def test_run_accepts_valid_status_transitions(current_status: WizardRunStatus, next_status: WizardRunStatus) -> None:
    assert transition(current_status, next_status) == next_status


@pytest.mark.parametrize("current_status, next_status", ILLEGAL_TRANSITIONS)
def test_run_rejects_invalid_status_transitions(current_status: WizardRunStatus, next_status: WizardRunStatus) -> None:
    with pytest.raises(IllegalStatusTransitionError):
        transition(current_status, next_status)
