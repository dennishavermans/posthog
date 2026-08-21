import logging
from uuid import UUID

from celery import shared_task
from celery.app.task import Task

from posthog.celery_queues import CeleryQueue

from products.wizard.backend.logic.runs.dispatch import WizardRunDispatchError, dispatch_run
from products.wizard.backend.tasks.config import DISPATCH_WIZARD_RUN_TASK

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    ignore_result=True,
    max_retries=5,
    name=DISPATCH_WIZARD_RUN_TASK,
    queue=CeleryQueue.DEFAULT.value,
)
def dispatch_wizard_run(self: Task, team_id: int, run_id: UUID) -> None:
    try:
        dispatch_run(team_id, run_id)
    except WizardRunDispatchError as error:
        logger.warning(
            "Retrying Wizard run dispatch",
            extra={"team_id": team_id, "run_id": str(run_id), "retry": self.request.retries},
        )
        raise self.retry(exc=error, countdown=min(2**self.request.retries, 60))
