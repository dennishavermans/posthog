from itertools import product

import pytest

from products.wizard.backend.facade.runs import (
    IllegalStatusTransitionError,
    InvalidTransitionMetadataError,
    MissingErrorCodeError,
    MissingOutcomeError,
    WizardRunErrorCode,
    WizardRunOutcome,
    WizardRunStatus,
)
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

# Transitions


@pytest.mark.parametrize("current_status, next_status", ALLOWED_TRANSITIONS)
def test_run_accepts_valid_status_transitions(current_status: WizardRunStatus, next_status: WizardRunStatus) -> None:
    outcome = WizardRunOutcome.CHANGES_CREATED if next_status == WizardRunStatus.COMPLETED else None
    error_code = WizardRunErrorCode.TIMEOUT if next_status == WizardRunStatus.FAILED else None

    assert transition(current_status, next_status, outcome=outcome, error_code=error_code) == next_status


@pytest.mark.parametrize("current_status, next_status", ILLEGAL_TRANSITIONS)
def test_run_rejects_invalid_status_transitions(current_status: WizardRunStatus, next_status: WizardRunStatus) -> None:
    with pytest.raises(IllegalStatusTransitionError):
        transition(current_status, next_status)


# Outcome reason


def test_completed_transition_requires_outcome() -> None:
    with pytest.raises(MissingOutcomeError):
        transition(WizardRunStatus.RUNNING, WizardRunStatus.COMPLETED)


# Errors


def test_failed_transition_requires_error_code() -> None:
    with pytest.raises(MissingErrorCodeError):
        transition(WizardRunStatus.RUNNING, WizardRunStatus.FAILED)


@pytest.mark.parametrize(
    ("current_status", "next_status", "outcome", "error_code"),
    [
        (WizardRunStatus.QUEUED, WizardRunStatus.RUNNING, WizardRunOutcome.CHANGES_CREATED, None),
        (
            WizardRunStatus.RUNNING,
            WizardRunStatus.COMPLETED,
            WizardRunOutcome.CHANGES_CREATED,
            WizardRunErrorCode.TIMEOUT,
        ),
    ],
)
def test_run_rejects_metadata_for_another_status(
    current_status: WizardRunStatus,
    next_status: WizardRunStatus,
    outcome: WizardRunOutcome | None,
    error_code: WizardRunErrorCode | None,
) -> None:
    with pytest.raises(InvalidTransitionMetadataError):
        transition(current_status, next_status, outcome=outcome, error_code=error_code)
