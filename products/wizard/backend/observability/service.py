import logging
from collections.abc import Callable

from products.wizard.backend.facade.contracts import WizardRunDTO, WizardRunPullRequestArtifactDTO
from products.wizard.backend.facade.enums import WizardRunStatus
from products.wizard.backend.observability.events import enqueue_run_event
from products.wizard.backend.observability.metrics import (
    report_git_diff_omitted,
    report_run_created,
    report_run_finished,
)

logger = logging.getLogger(__name__)

_TERMINAL_EVENTS = {
    WizardRunStatus.COMPLETED: "wizard run completed",
    WizardRunStatus.FAILED: "wizard run failed",
    WizardRunStatus.CANCELLED: "wizard run cancelled",
}


def _best_effort(operation: str, run: WizardRunDTO, action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:
        logger.exception(operation, extra={"team_id": run.team_id, "run_id": str(run.id)})


def terminal_event_name(status: WizardRunStatus) -> str:
    return _TERMINAL_EVENTS[status]


def run_created(run: WizardRunDTO) -> None:
    _best_effort("wizard_run_created_metric_failed", run, lambda: report_run_created(run))
    _best_effort("wizard_run_created_event_failed", run, lambda: enqueue_run_event(run, "wizard run created"))
    logger.info(
        "wizard_run_created",
        extra={"team_id": run.team_id, "run_id": str(run.id), "environment": run.environment.value},
    )


def run_transitioned(previous: WizardRunDTO, current: WizardRunDTO) -> None:
    if current.status not in _TERMINAL_EVENTS or previous.status == current.status:
        return
    _best_effort("wizard_run_finished_metric_failed", current, lambda: report_run_finished(current))
    _best_effort(
        "wizard_run_finished_event_failed",
        current,
        lambda: enqueue_run_event(current, terminal_event_name(current.status)),
    )
    logger.info(
        "wizard_run_finished",
        extra={
            "team_id": current.team_id,
            "run_id": str(current.id),
            "environment": current.environment.value,
            "status": current.status.value,
            "error_code": current.error_code.value if current.error_code is not None else None,
        },
    )


def git_diff_omitted(run: WizardRunDTO, size_bytes: int) -> None:
    _best_effort("wizard_git_diff_omitted_metric_failed", run, lambda: report_git_diff_omitted(run))
    logger.warning(
        "wizard_git_diff_omitted",
        extra={"team_id": run.team_id, "run_id": str(run.id), "size_bytes": size_bytes},
    )


def pull_request_created(run: WizardRunDTO, artifact: WizardRunPullRequestArtifactDTO) -> None:
    _best_effort(
        "wizard_pull_request_created_event_failed",
        run,
        lambda: enqueue_run_event(run, "wizard pull request created"),
    )
    logger.info(
        "wizard_pull_request_created",
        extra={
            "team_id": run.team_id,
            "run_id": str(run.id),
            "repository": artifact.repository,
            "pull_request_number": artifact.number,
        },
    )
