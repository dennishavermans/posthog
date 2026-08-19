from collections.abc import Mapping
from typing import cast

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    LocalFolderWorkspace,
    WizardWorkspace,
)
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardWorkspaceType
from products.wizard.backend.facade.errors import InvalidRepositoryError


class LocalFolderWorkspaceSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=[WizardWorkspaceType.LOCAL_FOLDER.value],
        help_text="Selects a folder on the user's machine as the workspace.",
    )
    project_name = serializers.CharField(
        allow_blank=False,
        max_length=255,
        help_text="Name of the project in the local folder.",
    )


class GitRepositoryWorkspaceSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=[WizardWorkspaceType.GIT_REPOSITORY.value],
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
    serializers=[LocalFolderWorkspaceSerializer, GitRepositoryWorkspaceSerializer],
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
            serializer = LocalFolderWorkspaceSerializer(data=workspace_data)
            serializer.is_valid(raise_exception=True)
            return LocalFolderWorkspace(project_name=cast(str, serializer.validated_data["project_name"]))
        if workspace_type == WizardWorkspaceType.GIT_REPOSITORY.value:
            serializer = GitRepositoryWorkspaceSerializer(data=workspace_data)
            serializer.is_valid(raise_exception=True)
            return GitRepositoryWorkspace(repository=cast(str, serializer.validated_data["repository"]))
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
        )
