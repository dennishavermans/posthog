from uuid import NAMESPACE_URL, uuid5

from celery import current_app as celery_app

from products.wizard.backend.facade.contracts import WizardRunDTO
from products.wizard.backend.observability.config import WIZARD_ANALYTICS_TASK


def enqueue_run_event(run: WizardRunDTO, event: str) -> None:
    event_uuid = uuid5(NAMESPACE_URL, f"wizard:{run.id}:{event}")
    celery_app.signature(
        WIZARD_ANALYTICS_TASK,
        args=[run.team_id, run.created_by_id, str(run.id), event, str(event_uuid)],
    ).apply_async()
