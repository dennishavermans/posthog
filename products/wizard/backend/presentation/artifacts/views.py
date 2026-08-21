from typing import cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.errors import WizardRunNotFoundError
from products.wizard.backend.presentation.artifacts.serializers import (
    WizardRunArtifactSchema,
    WizardRunArtifactSerializer,
    serialize_wizard_run_artifact,
)
from products.wizard.backend.presentation.runs.serializers import WizardRunErrorSerializer


class WizardRunArtifactViewSet(TeamAndOrgViewSetMixin, viewsets.GenericViewSet):
    scope_object = "wizard_session"
    scope_object_read_actions = ["list"]
    http_method_names = ["get", "head", "options"]
    pagination_class = None
    serializer_class = WizardRunArtifactSerializer

    @extend_schema(
        responses={
            200: WizardRunArtifactSchema,
            404: OpenApiResponse(response=WizardRunErrorSerializer),
        },
        description="List metadata for artifacts produced by a Wizard run.",
    )
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        # GET /projects/:projectId/wizard/runs/:runId/artifacts
        try:
            artifacts = wizard_facade.list_run_artifacts(self.team_id, self._run_id())
        except WizardRunNotFoundError:
            raise NotFound("No Wizard run was found for this project.")
        return Response([serialize_wizard_run_artifact(artifact) for artifact in artifacts])

    def _run_id(self) -> UUID:
        return UUID(cast(str, self.kwargs["parent_lookup_run_id"]))
