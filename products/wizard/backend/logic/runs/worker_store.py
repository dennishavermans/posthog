from uuid import UUID

from django.db.models import F
from django.utils import timezone

from products.wizard.backend.facade.enums import WizardWorkerCleanupStatus
from products.wizard.backend.models import WizardWorker


def get_sandbox_id(team_id: int, run_id: UUID) -> str | None:
    worker = WizardWorker.objects.for_team(team_id).filter(run_id=run_id).only("sandbox_id").first()
    return worker.sandbox_id if worker is not None else None


def record_provisioned_worker(team_id: int, run_id: UUID, sandbox_id: str) -> None:
    WizardWorker.objects.for_team(team_id).update_or_create(
        team_id=team_id,
        run_id=run_id,
        defaults={
            "sandbox_id": sandbox_id,
            "cleanup_status": WizardWorkerCleanupStatus.ACTIVE.value,
            "cleanup_error": None,
        },
    )


def mark_cleanup_pending(team_id: int, run_id: UUID) -> None:
    WizardWorker.objects.for_team(team_id).filter(run_id=run_id).update(
        cleanup_status=WizardWorkerCleanupStatus.PENDING.value,
        cleanup_attempts=F("cleanup_attempts") + 1,
        cleanup_error=None,
    )


def mark_cleanup_failed(team_id: int, run_id: UUID) -> None:
    WizardWorker.objects.for_team(team_id).filter(run_id=run_id).update(
        cleanup_status=WizardWorkerCleanupStatus.PENDING.value,
        cleanup_error="Wizard Worker cleanup failed.",
    )


def mark_cleaned(team_id: int, run_id: UUID) -> None:
    WizardWorker.objects.for_team(team_id).filter(run_id=run_id).update(
        cleanup_status=WizardWorkerCleanupStatus.CLEANED.value,
        cleanup_error=None,
        cleaned_at=timezone.now(),
    )
