from typing import cast
from uuid import UUID

from django.conf import settings

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.auth import SessionAuthentication
from posthog.exceptions import Conflict

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import WizardRunDTO
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.facade.errors import (
    IllegalStatusTransitionError,
    InvalidRepositoryError,
    InvalidWorkspaceEnvironmentError,
    MissingGitHubIntegrationError,
    RepositoryNotAccessibleError,
    WizardRunNotFoundError,
)
from products.wizard.backend.presentation.runs.pagination import WizardRunPagination
from products.wizard.backend.presentation.runs.serializers import (
    WizardRunArtifactSchema,
    WizardRunCreateRequestSerializer,
    WizardRunErrorSerializer,
    WizardRunSerializer,
    WizardRunStatusUpdateRequestSerializer,
    serialize_wizard_run_artifact,
)


class WizardRunViewSet(TeamAndOrgViewSetMixin, viewsets.GenericViewSet):
    scope_object = "wizard_session"
    scope_object_read_actions = ["list", "retrieve", "artifacts"]
    scope_object_write_actions = ["create", "partial_update"]
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_field = "run_id"
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    pagination_class = WizardRunPagination

    @extend_schema(
        responses={200: WizardRunSerializer(many=True)},
        description="List Wizard runs for this project, ordered from newest to oldest.",
    )
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        paginator = cast(WizardRunPagination, self.paginator)
        return paginator.paginate_runs(request, team_id=self.team_id)

    @extend_schema(
        request=WizardRunCreateRequestSerializer,
        responses={
            201: WizardRunSerializer,
            400: OpenApiResponse(response=WizardRunErrorSerializer),
            403: OpenApiResponse(response=WizardRunErrorSerializer),
            404: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Create a local or cloud Wizard run for a project workspace.",
    )
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = WizardRunCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.to_contract(team_id=self.team_id, created_by_id=cast(int, request.user.id))
        if params.environment == WizardRunEnvironment.CLOUD:
            self._validate_cloud_creation(request)
        try:
            run = wizard_facade.create_run(params)
        except InvalidWorkspaceEnvironmentError:
            raise ValidationError({"detail": "Choose a workspace supported by this run environment."})
        except InvalidRepositoryError:
            raise ValidationError({"detail": "Enter a repository in owner/name format."})
        except (MissingGitHubIntegrationError, RepositoryNotAccessibleError):
            raise ValidationError({"detail": "Connect GitHub with access to this repository, then try again."})
        return Response(WizardRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _validate_cloud_creation(request: Request) -> None:
        if not settings.WIZARD_CLOUD_RUN_OAUTH_CLIENT_ID:
            raise NotFound("Running the Wizard in the cloud is not available.")
        if not isinstance(request.successful_authenticator, SessionAuthentication):
            raise PermissionDenied("Sign in to start a cloud Wizard run.")

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
            200: WizardRunArtifactSchema,
            404: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="List metadata for artifacts produced by a Wizard run.",
    )
    @action(detail=True, methods=["get"], pagination_class=None)
    def artifacts(self, request: Request, *args: object, **kwargs: object) -> Response:
        run_id = self._run_id()
        try:
            artifacts = wizard_facade.list_run_artifacts(self.team_id, run_id)
        except WizardRunNotFoundError:
            raise NotFound("No Wizard run was found for this project.")
        return Response([serialize_wizard_run_artifact(artifact) for artifact in artifacts])

    @extend_schema(
        request=WizardRunStatusUpdateRequestSerializer,
        responses={
            200: WizardRunSerializer,
            400: OpenApiResponse(response=WizardRunErrorSerializer),
            403: OpenApiResponse(response=WizardRunErrorSerializer),
            404: OpenApiResponse(response=WizardRunErrorSerializer),
            409: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="Change the terminal status of a local Wizard run.",
    )
    def partial_update(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = WizardRunStatusUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_status = serializer.to_status()
        try:
            run = wizard_facade.transition_run(
                self.team_id,
                self._local_run_id(),
                next_status,
                error_code=serializer.to_error_code(),
            )
        except IllegalStatusTransitionError:
            raise Conflict(
                f"This Wizard run cannot be {next_status.value} from its current status.",
                code="invalid_transition",
            )
        return Response(WizardRunSerializer(run).data)

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
