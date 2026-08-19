from hashlib import sha256
from uuid import UUID

from posthog.storage import object_storage

from products.wizard.backend.facade.contracts import WizardRunArtifactDTO
from products.wizard.backend.facade.enums import WizardRunArtifactType
from products.wizard.backend.logic.run_store import get_run_model
from products.wizard.backend.models import WizardRunArtifact

GIT_DIFF_CONTENT_TYPE = "text/x-diff; charset=utf-8"


def create_git_diff_artifact(team_id: int, run_id: UUID, content: bytes) -> WizardRunArtifactDTO | None:
    if not content:
        return None

    run = get_run_model(team_id, run_id)
    storage_path = _git_diff_storage_path(team_id, run_id)
    object_storage.write(storage_path, content, extras={"ContentType": GIT_DIFF_CONTENT_TYPE})
    artifact, _ = WizardRunArtifact.objects.for_team(team_id).update_or_create(
        run_id=run.id,
        type=WizardRunArtifactType.GIT_DIFF.value,
        defaults={
            "team_id": team_id,
            "storage_path": storage_path,
            "size_bytes": len(content),
            "content_hash": sha256(content).hexdigest(),
        },
    )
    return _to_dto(artifact)


def list_run_artifacts(team_id: int, run_id: UUID) -> list[WizardRunArtifactDTO]:
    run = get_run_model(team_id, run_id)
    artifacts = WizardRunArtifact.objects.for_team(team_id).filter(run_id=run.id).order_by("created_at", "id")
    return [_to_dto(artifact) for artifact in artifacts]


def _git_diff_storage_path(team_id: int, run_id: UUID) -> str:
    return f"wizard/runs/team_{team_id}/run_{run_id}/artifacts/git.diff"


def _to_dto(artifact: WizardRunArtifact) -> WizardRunArtifactDTO:
    return WizardRunArtifactDTO(
        id=artifact.id,
        team_id=artifact.team_id,
        run_id=artifact.run_id,
        artifact_type=WizardRunArtifactType(artifact.type),
        size_bytes=artifact.size_bytes,
        content_hash=artifact.content_hash,
        created_at=artifact.created_at,
    )
