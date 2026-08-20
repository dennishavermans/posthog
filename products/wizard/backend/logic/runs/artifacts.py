from hashlib import sha256
from typing import cast
from uuid import UUID

from posthog.storage import object_storage

from products.wizard.backend.facade.contracts import (
    CreatePullRequestArtifactInput,
    WizardRunArtifactDTO,
    WizardRunGitDiffArtifactDTO,
    WizardRunPullRequestArtifactDTO,
)
from products.wizard.backend.facade.enums import WizardRunArtifactType
from products.wizard.backend.logic.runs.store import get_run_model
from products.wizard.backend.models import WizardRunArtifact

GIT_DIFF_CONTENT_TYPE = "text/x-diff; charset=utf-8"


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
    return _to_git_diff_dto(artifact)


def create_pull_request_artifact(params: CreatePullRequestArtifactInput) -> WizardRunPullRequestArtifactDTO:
    run = get_run_model(params.team_id, params.run_id)
    artifact, _ = WizardRunArtifact.objects.for_team(params.team_id).update_or_create(
        run_id=run.id,
        type=WizardRunArtifactType.PULL_REQUEST.value,
        defaults={
            "team_id": params.team_id,
            "storage_path": None,
            "external_url": params.url,
            "metadata": {
                "number": params.number,
                "repository": params.repository,
                "head_branch": params.head_branch,
                "base_branch": params.base_branch,
            },
            "size_bytes": None,
            "content_hash": None,
        },
    )
    return _to_pull_request_dto(artifact)


def list_run_artifacts(team_id: int, run_id: UUID) -> list[WizardRunArtifactDTO]:
    run = get_run_model(team_id, run_id)
    artifacts = WizardRunArtifact.objects.for_team(team_id).filter(run_id=run.id).order_by("created_at", "id")
    return [_to_dto(artifact) for artifact in artifacts]


def _git_diff_storage_path(team_id: int, run_id: UUID) -> str:
    return f"wizard/runs/team_{team_id}/run_{run_id}/artifacts/git.diff"


def _to_dto(artifact: WizardRunArtifact) -> WizardRunArtifactDTO:
    artifact_type = WizardRunArtifactType(artifact.type)
    if artifact_type == WizardRunArtifactType.GIT_DIFF:
        return _to_git_diff_dto(artifact)
    return _to_pull_request_dto(artifact)


def _to_git_diff_dto(artifact: WizardRunArtifact) -> WizardRunGitDiffArtifactDTO:
    if artifact.size_bytes is None or artifact.content_hash is None:
        raise ValueError("Git diff artifact is missing stored content metadata.")
    return WizardRunGitDiffArtifactDTO(
        id=artifact.id,
        team_id=artifact.team_id,
        run_id=artifact.run_id,
        artifact_type=WizardRunArtifactType.GIT_DIFF,
        size_bytes=artifact.size_bytes,
        content_hash=artifact.content_hash,
        created_at=artifact.created_at,
    )


def _to_pull_request_dto(artifact: WizardRunArtifact) -> WizardRunPullRequestArtifactDTO:
    metadata = cast(dict[str, object], artifact.metadata or {})
    number = metadata.get("number")
    repository = metadata.get("repository")
    head_branch = metadata.get("head_branch")
    base_branch = metadata.get("base_branch")
    if (
        artifact.external_url is None
        or not isinstance(number, int)
        or not isinstance(repository, str)
        or not isinstance(head_branch, str)
        or not isinstance(base_branch, str)
    ):
        raise ValueError("Pull request artifact is missing repository metadata.")
    return WizardRunPullRequestArtifactDTO(
        id=artifact.id,
        team_id=artifact.team_id,
        run_id=artifact.run_id,
        artifact_type=WizardRunArtifactType.PULL_REQUEST,
        url=artifact.external_url,
        number=number,
        repository=repository,
        head_branch=head_branch,
        base_branch=base_branch,
        created_at=artifact.created_at,
    )
