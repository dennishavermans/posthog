from collections.abc import Mapping
from typing import cast

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    LocalFolderWorkspace,
    WizardRunArtifactDTO,
    WizardRunGitDiffArtifactDTO,
    WizardRunPullRequestArtifactDTO,
    WizardWorkspace,
)
from products.wizard.backend.facade.enums import (
    WizardRunArtifactType,
    WizardRunEnvironment,
    WizardRunErrorCode,
    WizardRunStatus,
    WizardWorkspaceType,
)
from products.wizard.backend.facade.errors import InvalidRepositoryError


class WizardWorkspaceTypeField(serializers.CharField):
    workspace_type: WizardWorkspaceType

    def to_internal_value(self, data: object) -> str:
        value = super().to_internal_value(cast(str, data))
        if value != self.workspace_type.value:
            self.fail("invalid")
        return value


@extend_schema_field({"type": "string", "const": WizardWorkspaceType.LOCAL_FOLDER.value})
class LocalFolderWorkspaceTypeField(WizardWorkspaceTypeField):
    workspace_type = WizardWorkspaceType.LOCAL_FOLDER


@extend_schema_field({"type": "string", "const": WizardWorkspaceType.GIT_REPOSITORY.value})
class GitRepositoryWorkspaceTypeField(WizardWorkspaceTypeField):
    workspace_type = WizardWorkspaceType.GIT_REPOSITORY


class LocalFolderWorkspaceSerializer(serializers.Serializer):
    type = LocalFolderWorkspaceTypeField(
        help_text="Selects a folder on the user's machine as the workspace.",
    )
    project_name = serializers.CharField(
        allow_blank=False,
        max_length=255,
        help_text="Name of the project in the local folder.",
    )


class GitRepositoryWorkspaceSerializer(serializers.Serializer):
    type = GitRepositoryWorkspaceTypeField(
        help_text="Selects a GitHub repository as the workspace.",
    )
    repository = serializers.CharField(
        allow_blank=False,
        max_length=255,
        help_text="GitHub repository in owner/name format.",
    )

    def validate_repository(self, value: str) -> str:
        repository = value.strip()
        try:
            wizard_facade.validate_git_repository(repository)
        except InvalidRepositoryError:
            raise serializers.ValidationError("Enter a repository in owner/name format.")
        return repository


WizardWorkspaceSchema = PolymorphicProxySerializer(
    component_name="WizardWorkspace",
    serializers={
        WizardWorkspaceType.LOCAL_FOLDER.value: LocalFolderWorkspaceSerializer,
        WizardWorkspaceType.GIT_REPOSITORY.value: GitRepositoryWorkspaceSerializer,
    },
    resource_type_field_name="type",
)


@extend_schema_field(WizardWorkspaceSchema)
class WizardWorkspaceField(serializers.Field):
    def to_internal_value(self, data: object) -> WizardWorkspace:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError("Enter a workspace object.")

        workspace_data = cast(Mapping[str, object], data)
        workspace_type = workspace_data.get("type")
        if workspace_type == WizardWorkspaceType.LOCAL_FOLDER.value:
            local_serializer = LocalFolderWorkspaceSerializer(data=workspace_data)
            local_serializer.is_valid(raise_exception=True)
            return LocalFolderWorkspace(project_name=cast(str, local_serializer.validated_data["project_name"]))
        if workspace_type == WizardWorkspaceType.GIT_REPOSITORY.value:
            repository_serializer = GitRepositoryWorkspaceSerializer(data=workspace_data)
            repository_serializer.is_valid(raise_exception=True)
            return GitRepositoryWorkspace(repository=cast(str, repository_serializer.validated_data["repository"]))
        if "type" not in workspace_data:
            raise serializers.ValidationError({"type": ["This field is required."]})
        raise serializers.ValidationError({"type": ["Select a valid workspace type."]})

    def to_representation(self, value: WizardWorkspace) -> dict[str, object]:
        if isinstance(value, LocalFolderWorkspace):
            return cast(dict[str, object], LocalFolderWorkspaceSerializer(value).data)
        if isinstance(value, GitRepositoryWorkspace):
            return cast(dict[str, object], GitRepositoryWorkspaceSerializer(value).data)
        raise TypeError("Unsupported Wizard workspace")


class WizardRunCreateRequestSerializer(serializers.Serializer):
    program_id = serializers.RegexField(
        regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        help_text="Registry program to run.",
    )
    environment = serializers.ChoiceField(
        choices=[environment.value for environment in WizardRunEnvironment],
        help_text="Where the setup agent runs.",
    )
    workspace = WizardWorkspaceField(
        help_text="Project that the setup agent works on.",
    )

    def to_contract(self, *, team_id: int, created_by_id: int) -> CreateWizardRunInput:
        return CreateWizardRunInput(
            team_id=team_id,
            created_by_id=created_by_id,
            environment=WizardRunEnvironment(cast(str, self.validated_data["environment"])),
            workspace=cast(WizardWorkspace, self.validated_data["workspace"]),
            program_id=cast(str, self.validated_data["program_id"]),
        )


class WizardRunStatusUpdateRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            WizardRunStatus.COMPLETED.value,
            WizardRunStatus.FAILED.value,
            WizardRunStatus.CANCELLED.value,
        ],
        help_text="New terminal status for the Wizard run.",
    )
    error_code = serializers.ChoiceField(
        required=False,
        allow_null=True,
        choices=[error_code.value for error_code in WizardRunErrorCode],
        help_text="Machine-readable reason the Wizard run failed.",
    )

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs.get("error_code") is not None and attrs["status"] != WizardRunStatus.FAILED.value:
            raise serializers.ValidationError({"error_code": "Only failed runs can have an error code."})
        return attrs

    def to_status(self) -> WizardRunStatus:
        return WizardRunStatus(cast(str, self.validated_data["status"]))

    def to_error_code(self) -> WizardRunErrorCode | None:
        value = cast(str | None, self.validated_data.get("error_code"))
        return WizardRunErrorCode(value) if value is not None else None


class WizardRunSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, help_text="Unique ID of the Wizard run.")
    team_id = serializers.IntegerField(read_only=True, help_text="Project that owns the Wizard run.")
    created_by_id = serializers.IntegerField(
        read_only=True,
        allow_null=True,
        help_text="User who created the Wizard run, or null if that user no longer exists.",
    )
    environment = serializers.ChoiceField(
        read_only=True,
        choices=[environment.value for environment in WizardRunEnvironment],
        help_text="Where the setup agent runs.",
    )
    workspace = WizardWorkspaceField(read_only=True, help_text="Project that the setup agent works on.")
    status = serializers.ChoiceField(
        read_only=True,
        choices=[run_status.value for run_status in WizardRunStatus],
        help_text="Current lifecycle status of the Wizard run.",
    )
    error_code = serializers.ChoiceField(
        read_only=True,
        allow_null=True,
        choices=[error_code.value for error_code in WizardRunErrorCode],
        help_text="Machine-readable failure reason, or null if the run has not failed.",
    )


class WizardRunArtifactSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, help_text="Unique ID of the run artifact.")
    team_id = serializers.IntegerField(read_only=True, help_text="Project that owns the run artifact.")
    run_id = serializers.UUIDField(read_only=True, help_text="Wizard run that produced the artifact.")


class WizardRunGitDiffArtifactSerializer(WizardRunArtifactSerializer):
    artifact_type = serializers.ChoiceField(
        read_only=True,
        choices=[WizardRunArtifactType.GIT_DIFF.value],
        help_text="Format of the changes produced by the run.",
    )
    size_bytes = serializers.IntegerField(read_only=True, help_text="Stored artifact size in bytes.")
    content_hash = serializers.CharField(read_only=True, help_text="SHA-256 hash of the stored artifact content.")
    created_at = serializers.DateTimeField(read_only=True, help_text="Time when the artifact was stored.")


class WizardRunPullRequestArtifactSerializer(WizardRunArtifactSerializer):
    artifact_type = serializers.ChoiceField(
        read_only=True,
        choices=[WizardRunArtifactType.PULL_REQUEST.value],
        help_text="Format of the changes produced by the run.",
    )
    url = serializers.URLField(read_only=True, help_text="GitHub URL of the pull request.")
    number = serializers.IntegerField(read_only=True, help_text="Repository-local pull request number.")
    repository = serializers.CharField(read_only=True, help_text="GitHub repository in owner/name format.")
    head_branch = serializers.CharField(read_only=True, help_text="Branch containing the setup agent's changes.")
    base_branch = serializers.CharField(read_only=True, help_text="Branch that the pull request targets.")
    created_at = serializers.DateTimeField(read_only=True, help_text="Time when the artifact was stored.")


WizardRunArtifactSchema = PolymorphicProxySerializer(
    component_name="WizardRunArtifact",
    serializers={
        WizardRunArtifactType.GIT_DIFF.value: WizardRunGitDiffArtifactSerializer,
        WizardRunArtifactType.PULL_REQUEST.value: WizardRunPullRequestArtifactSerializer,
    },
    resource_type_field_name="artifact_type",
    many=True,
)


def serialize_wizard_run_artifact(artifact: WizardRunArtifactDTO) -> dict[str, object]:
    if isinstance(artifact, WizardRunGitDiffArtifactDTO):
        return cast(dict[str, object], WizardRunGitDiffArtifactSerializer(artifact).data)
    if isinstance(artifact, WizardRunPullRequestArtifactDTO):
        return cast(dict[str, object], WizardRunPullRequestArtifactSerializer(artifact).data)
    raise TypeError("Unsupported Wizard run artifact")


class WizardRunErrorSerializer(serializers.Serializer):
    type = serializers.CharField(read_only=True, help_text="Error category.")
    code = serializers.CharField(read_only=True, help_text="Machine-readable error code.")
    detail = serializers.CharField(read_only=True, help_text="What happened and how to continue.")
    attr = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="Request field associated with the error, when available.",
    )
