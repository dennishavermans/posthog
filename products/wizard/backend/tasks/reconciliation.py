from celery import shared_task
from prometheus_client import Gauge

from posthog.celery_queues import CeleryQueue
from posthog.tasks.utils import PushGatewayTask

from products.wizard.backend.logic.runs import reconciliation
from products.wizard.backend.tasks.config import RECONCILE_WIZARD_RUNS_TASK


@shared_task(
    bind=True,
    base=PushGatewayTask,
    ignore_result=True,
    name=RECONCILE_WIZARD_RUNS_TASK,
    queue=CeleryQueue.DEFAULT.value,
)
def reconcile_wizard_runs(self: PushGatewayTask) -> None:
    results = {
        "dispatch": reconciliation.reconcile_pending_dispatches(),
        "cancellation": reconciliation.reconcile_pending_cancellations(),
        "expiration": reconciliation.reconcile_expired_runs(),
        "cleanup": reconciliation.reconcile_pending_worker_cleanup(),
    }
    if self.metrics_registry is None:
        return
    reconciled = Gauge(
        "posthog_wizard_run_reconciled_total",
        "Wizard run records recovered by the reconciliation sweep",
        labelnames=["operation"],
        registry=self.metrics_registry,
    )
    for operation, count in results.items():
        reconciled.labels(operation=operation).set(count)
