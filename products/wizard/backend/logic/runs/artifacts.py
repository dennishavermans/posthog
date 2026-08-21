from hashlib import sha256
from uuid import UUID

from posthog.storage import object_storage

from products.wizard.backend.facade.contracts import (
    CreatePullRequestArtifactInput,
    WizardRunArtifactDTO,
    WizardRunGitDiffArtifactDTO,
    WizardRunPullRequestArtifactDTO,
)
from products.wizard.backend.facade.enums import WizardRunArtifactType
from products.wizard.backend.logic.runs.config import GIT_DIFF_CONTENT_TYPE
from products.wizard.backend.logic.runs.serializers import serialize_pull_request_metadata, to_artifact_dto
from products.wizard.backend.logic.runs.store import get_run_model
from products.wizard.backend.models import WizardRunArtifact


def create_git_diff_artifact(team_id: int, run_id: UUID, content: bytes) -> WizardRunGitDiffArtifactDTO | None:
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
            "external_url": None,
            "metadata": None,
            "size_bytes": len(content),
            "content_hash": sha256(content).hexdigest(),
        },
    )
    artifact_dto = to_artifact_dto(artifact)
    if not isinstance(artifact_dto, WizardRunGitDiffArtifactDTO):
        raise ValueError("Expected a git diff artifact")
    return artifact_dto


def create_pull_request_artifact(params: CreatePullRequestArtifactInput) -> WizardRunPullRequestArtifactDTO:
    run = get_run_model(params.team_id, params.run_id)
    artifact, _ = WizardRunArtifact.objects.for_team(params.team_id).update_or_create(
        run_id=run.id,
        type=WizardRunArtifactType.PULL_REQUEST.value,
        defaults={
            "team_id": params.team_id,
            "storage_path": None,
            "external_url": params.url,
            "metadata": serialize_pull_request_metadata(
                params.number,
                params.repository,
                params.head_branch,
                params.base_branch,
            ),
            "size_bytes": None,
            "content_hash": None,
        },
    )
    artifact_dto = to_artifact_dto(artifact)
    if not isinstance(artifact_dto, WizardRunPullRequestArtifactDTO):
        raise ValueError("Expected a pull request artifact")
    return artifact_dto


def list_run_artifacts(team_id: int, run_id: UUID) -> list[WizardRunArtifactDTO]:
    run = get_run_model(team_id, run_id)
    artifacts = WizardRunArtifact.objects.for_team(team_id).filter(run_id=run.id).order_by("created_at", "id")
    return [to_artifact_dto(artifact) for artifact in artifacts]


def _git_diff_storage_path(team_id: int, run_id: UUID) -> str:
    return f"wizard/runs/team_{team_id}/run_{run_id}/artifacts/git.diff"
