from uuid import UUID

from products.wizard.backend.facade.contracts import (
    WizardRunArtifactDTO,
    WizardRunGitDiffArtifactDTO,
    WizardRunPullRequestArtifactDTO,
)
from products.wizard.backend.facade.enums import WizardRunArtifactType
from products.wizard.backend.logic.artifacts.mappers import artifact_from_record, pull_request_metadata_to_record
from products.wizard.backend.models import WizardRunArtifact


def upsert_git_diff(
    *,
    team_id: int,
    run_id: UUID,
    storage_path: str,
    size_bytes: int,
    content_hash: str,
    additions: int,
    removals: int,
) -> WizardRunGitDiffArtifactDTO:
    artifact, _ = WizardRunArtifact.objects.for_team(team_id).update_or_create(
        run_id=run_id,
        type=WizardRunArtifactType.GIT_DIFF.value,
        defaults={
            "team_id": team_id,
            "storage_path": storage_path,
            "external_url": None,
            "metadata": {"additions": additions, "removals": removals},
            "size_bytes": size_bytes,
            "content_hash": content_hash,
        },
    )
    result = artifact_from_record(artifact)
    if not isinstance(result, WizardRunGitDiffArtifactDTO):
        raise ValueError("Expected a git diff artifact")
    return result


def upsert_pull_request(
    *,
    team_id: int,
    run_id: UUID,
    url: str,
    number: int,
    repository: str,
    head_branch: str,
    base_branch: str,
) -> WizardRunPullRequestArtifactDTO:
    artifact, _ = WizardRunArtifact.objects.for_team(team_id).update_or_create(
        run_id=run_id,
        type=WizardRunArtifactType.PULL_REQUEST.value,
        defaults={
            "team_id": team_id,
            "storage_path": None,
            "external_url": url,
            "metadata": pull_request_metadata_to_record(number, repository, head_branch, base_branch),
            "size_bytes": None,
            "content_hash": None,
        },
    )
    result = artifact_from_record(artifact)
    if not isinstance(result, WizardRunPullRequestArtifactDTO):
        raise ValueError("Expected a pull request artifact")
    return result


def list_artifacts(team_id: int, run_id: UUID) -> list[WizardRunArtifactDTO]:
    artifacts = WizardRunArtifact.objects.for_team(team_id).filter(run_id=run_id).order_by("created_at", "id")
    return [artifact_from_record(artifact) for artifact in artifacts]


def get_git_diff_storage_path(team_id: int, run_id: UUID, artifact_id: UUID) -> str | None:
    storage_path = (
        WizardRunArtifact.objects.for_team(team_id)
        .filter(id=artifact_id, run_id=run_id, type=WizardRunArtifactType.GIT_DIFF.value)
        .values_list("storage_path", flat=True)
        .first()
    )
    return storage_path if isinstance(storage_path, str) else None
