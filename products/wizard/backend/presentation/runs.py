from collections.abc import Callable, Mapping
from functools import partial
from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, PolymorphicProxySerializer, extend_schema, extend_schema_field
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.exceptions import Conflict

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    LocalFolderWorkspace,
    WizardRunDTO,
    WizardWorkspace,
)
from products.wizard.backend.facade.enums import (
    WizardRunArtifactType,
    WizardRunEnvironment,
    WizardRunErrorCode,
    WizardRunStatus,
    WizardWorkspaceType,
)
from products.wizard.backend.facade.errors import (
    IllegalStatusTransitionError,
    InvalidRepositoryError,
    InvalidWorkspaceEnvironmentError,
    MissingGitHubIntegrationError,
    RepositoryNotAccessibleError,
    WizardRunNotFoundError,
)


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


class WizardRunFailureRequestSerializer(serializers.Serializer):
    error_code = serializers.ChoiceField(
        required=False,
        allow_null=True,
        choices=[error_code.value for error_code in WizardRunErrorCode],
        help_text="Machine-readable reason the Wizard run failed.",
    )

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
    artifact_type = serializers.ChoiceField(
        read_only=True,
        choices=[artifact_type.value for artifact_type in WizardRunArtifactType],
        help_text="Format of the changes produced by the run.",
    )
    size_bytes = serializers.IntegerField(read_only=True, help_text="Stored artifact size in bytes.")
    content_hash = serializers.CharField(read_only=True, help_text="SHA-256 hash of the stored artifact content.")
    created_at = serializers.DateTimeField(read_only=True, help_text="Time when the artifact was stored.")


class WizardRunErrorSerializer(serializers.Serializer):
    type = serializers.CharField(read_only=True, help_text="Error category.")
    code = serializers.CharField(read_only=True, help_text="Machine-readable error code.")
    detail = serializers.CharField(read_only=True, help_text="What happened and how to continue.")
    attr = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="Request field associated with the error, when available.",
    )


class WizardRunViewSet(TeamAndOrgViewSetMixin, viewsets.GenericViewSet):
    scope_object = "wizard_session"
    scope_object_read_actions = ["retrieve", "artifacts"]
    scope_object_write_actions = ["create", "complete", "fail", "cancel"]
    http_method_names = ["get", "post", "head", "options"]
    lookup_field = "run_id"
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    pagination_class = None

    @extend_schema(
        request=WizardRunCreateRequestSerializer,
        responses={
            201: WizardRunSerializer,
            400: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Create a local or cloud Wizard run for a project workspace.",
    )
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = WizardRunCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            run = wizard_facade.create_run(
                serializer.to_contract(team_id=self.team_id, created_by_id=cast(int, request.user.id))
            )
        except InvalidWorkspaceEnvironmentError:
            raise ValidationError({"detail": "Choose a workspace supported by this run environment."})
        except InvalidRepositoryError:
            raise ValidationError({"detail": "Enter a repository in owner/name format."})
        except (MissingGitHubIntegrationError, RepositoryNotAccessibleError):
            raise ValidationError({"detail": "Connect GitHub with access to this repository, then try again."})
        return Response(WizardRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={
            200: WizardRunSerializer,
            404: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Retrieve a Wizard run in this project.",
    )
    def retrieve(self, request: Request, *args: object, **kwargs: object) -> Response:
        run = self._get_run()
        return Response(WizardRunSerializer(run).data)

    @extend_schema(
        responses={
            200: WizardRunArtifactSerializer(many=True),
            404: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="List metadata for artifacts produced by a Wizard run.",
    )
    @action(detail=True, methods=["get"])
    def artifacts(self, request: Request, *args: object, **kwargs: object) -> Response:
        run_id = self._run_id()
        try:
            artifacts = wizard_facade.list_run_artifacts(self.team_id, run_id)
        except WizardRunNotFoundError:
            raise NotFound("No Wizard run was found for this project.")
        return Response(WizardRunArtifactSerializer(artifacts, many=True).data)

    @extend_schema(
        request=None,
        responses={
            200: WizardRunSerializer,
            403: OpenApiResponse(response=WizardRunErrorSerializer),
            404: OpenApiResponse(response=WizardRunErrorSerializer),
            409: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Complete a local Wizard run.",
    )
    @action(detail=True, methods=["post"])
    def complete(self, request: Request, *args: object, **kwargs: object) -> Response:
        return self._transition_local_run(wizard_facade.complete_run, "completed")

    @extend_schema(
        request=WizardRunFailureRequestSerializer,
        responses={
            200: WizardRunSerializer,
            400: OpenApiResponse(response=WizardRunErrorSerializer),
            403: OpenApiResponse(response=WizardRunErrorSerializer),
            404: OpenApiResponse(response=WizardRunErrorSerializer),
            409: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Fail a local Wizard run.",
    )
    @action(detail=True, methods=["post"])
    def fail(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = WizardRunFailureRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        operation = partial(wizard_facade.fail_run, error_code=serializer.to_error_code())
        return self._transition_local_run(operation, "failed")

    @extend_schema(
        request=None,
        responses={
            200: WizardRunSerializer,
            403: OpenApiResponse(response=WizardRunErrorSerializer),
            404: OpenApiResponse(response=WizardRunErrorSerializer),
            409: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Cancel a local Wizard run.",
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, *args: object, **kwargs: object) -> Response:
        return self._transition_local_run(wizard_facade.cancel_run, "cancelled")

    def _get_run(self) -> WizardRunDTO:
        try:
            return wizard_facade.get_run(self.team_id, self._run_id())
        except WizardRunNotFoundError:
            raise NotFound("No Wizard run was found for this project.")

    def _run_id(self) -> UUID:
        return UUID(cast(str, self.kwargs["run_id"]))

    def _local_run_id(self) -> UUID:
        run = self._get_run()
        if run.environment != WizardRunEnvironment.LOCAL:
            raise Conflict("Cloud Wizard runs are managed by their worker.", code="cloud_run_managed")
        if run.created_by_id != self.request.user.id:
            raise PermissionDenied("Only the user who started this Wizard run can update it.")
        return run.id

    def _transition_local_run(
        self,
        operation: Callable[[int, UUID], WizardRunDTO],
        next_status: str,
    ) -> Response:
        try:
            run = operation(self.team_id, self._local_run_id())
        except IllegalStatusTransitionError:
            raise Conflict(
                f"This Wizard run cannot be {next_status} from its current status.",
                code="invalid_transition",
            )
        return Response(WizardRunSerializer(run).data)
