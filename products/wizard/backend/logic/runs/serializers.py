from products.wizard.backend.facade.contracts import (
    WizardRunArtifactDTO,
    WizardRunDTO,
    WizardRunGitDiffArtifactDTO,
    WizardRunPullRequestArtifactDTO,
)
from products.wizard.backend.facade.enums import (
    WizardRunArtifactType,
    WizardRunEnvironment,
    WizardRunErrorCode,
    WizardRunStatus,
)
from products.wizard.backend.facade.serializers.programs import WIZARD_PROGRAM_SERIALIZER
from products.wizard.backend.facade.serializers.workspaces import WIZARD_WORKSPACE_SERIALIZER
from products.wizard.backend.models import WizardRun, WizardRunArtifact


def to_run_dto(run: WizardRun) -> WizardRunDTO:
    return WizardRunDTO(
        id=run.id,
        team_id=run.team_id,
        created_by_id=run.created_by_id,
        environment=WizardRunEnvironment(run.environment),
        workspace=WIZARD_WORKSPACE_SERIALIZER.deserialize(run.workspace_type, run.workspace),
        program=WIZARD_PROGRAM_SERIALIZER.deserialize_persisted(run.program),
        status=WizardRunStatus(run.status),
        error_code=WizardRunErrorCode(run.error_code) if run.error_code else None,
    )


def to_artifact_dto(artifact: WizardRunArtifact) -> WizardRunArtifactDTO:
    if WizardRunArtifactType(artifact.type) == WizardRunArtifactType.GIT_DIFF:
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

    metadata = artifact.metadata or {}
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


def serialize_pull_request_metadata(
    number: int, repository: str, head_branch: str, base_branch: str
) -> dict[str, object]:
    return {
        "number": number,
        "repository": repository,
        "head_branch": head_branch,
        "base_branch": base_branch,
    }
