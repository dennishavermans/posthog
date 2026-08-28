from typing import Any

from django.db import models

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.event_usage import report_user_action

from products.access_control.backend.facade.user_access_control import UserAccessControl
from products.dashboards.backend.feature_flags import dashboard_saved_views_enabled
from products.dashboards.backend.models.dashboard import Dashboard
from products.dashboards.backend.models.dashboard_saved_view import DashboardSavedView

SAVED_VIEW_FILTER_KEYS = {"search", "createdBy", "pinned", "shared", "tags", "folder"}


def saved_view_filter_properties(filters: dict[str, Any]) -> dict[str, bool | int]:
    tags = filters.get("tags", [])
    tag_count = len(tags) if isinstance(tags, list) else 0
    has_search = bool(filters.get("search"))
    has_folder = filters.get("folder") is not None
    has_tags = tag_count > 0
    created_by = filters.get("createdBy")
    has_creator = isinstance(created_by, list) and len(created_by) > 0
    is_pinned = bool(filters.get("pinned"))
    is_shared = bool(filters.get("shared"))

    return {
        "has_search_filter": has_search,
        "has_folder_filter": has_folder,
        "has_tag_filter": has_tags,
        "tag_count": tag_count,
        "has_creator_filter": has_creator,
        "is_pinned": is_pinned,
        "is_shared": is_shared,
        "active_filter_count": sum([has_search, has_folder, has_tags, has_creator, is_pinned, is_shared]),
    }


def has_saved_view_filters(filters: dict[str, Any]) -> bool:
    return any(
        saved_view_filter_properties(filters)[property]
        for property in [
            "has_search_filter",
            "has_folder_filter",
            "has_tag_filter",
            "has_creator_filter",
            "is_pinned",
            "is_shared",
        ]
    )


def saved_view_creator_properties(*, team_id: int, user_id: int) -> dict[str, int]:
    return {
        "saved_views_created_by_user_count": DashboardSavedView.objects.for_team(team_id)
        .filter(created_by_id=user_id)
        .count(),
        "dashboards_created_by_user_count": Dashboard.objects.filter(team_id=team_id, created_by_id=user_id).count(),
    }


@extend_schema_field(OpenApiTypes.OBJECT)
class DashboardSavedViewFiltersField(serializers.JSONField):
    pass


class DashboardSavedViewWriteSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=200, help_text="Name shown in the dashboard list view picker.")
    filters = DashboardSavedViewFiltersField(help_text="Dashboard list filters stored by this view.")
    scope = serializers.ChoiceField(
        choices=DashboardSavedView.Scope.choices,
        default=DashboardSavedView.Scope.PRIVATE,
        help_text="Whether only the creator or all team members can use this view.",
    )

    class Meta:
        model = DashboardSavedView
        fields = ["name", "filters", "scope"]

    def validate_filters(self, value: dict) -> dict:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filters must be an object")
        unsupported_keys = value.keys() - SAVED_VIEW_FILTER_KEYS
        if unsupported_keys:
            raise serializers.ValidationError("Filters contain unsupported fields.")
        if "search" in value and not isinstance(value["search"], str):
            raise serializers.ValidationError("Search must be a string.")
        if "createdBy" in value and value["createdBy"] != "All users":
            creators = value["createdBy"]
            if not isinstance(creators, list) or any(type(creator) is not int for creator in creators):
                raise serializers.ValidationError("Creators must be a list of user IDs.")
        if "pinned" in value and not isinstance(value["pinned"], bool):
            raise serializers.ValidationError("Pinned must be true or false.")
        if "shared" in value and not isinstance(value["shared"], bool):
            raise serializers.ValidationError("Shared must be true or false.")
        if "tags" in value and (
            not isinstance(value["tags"], list) or any(not isinstance(tag, str) for tag in value["tags"])
        ):
            raise serializers.ValidationError("Tags must be a list of strings.")
        if "folder" in value and value["folder"] is not None and not isinstance(value["folder"], str):
            raise serializers.ValidationError("Folder must be a string or null.")
        if not has_saved_view_filters(value):
            raise serializers.ValidationError("Add at least one filter before saving a view.")
        return value


class DashboardSavedViewSerializer(DashboardSavedViewWriteSerializer):
    class Meta(DashboardSavedViewWriteSerializer.Meta):
        fields = ["id", "name", "filters", "scope", "created_at", "updated_at", "created_by"]
        read_only_fields = ["id", "created_at", "updated_at", "created_by"]


class DashboardSavedViewPagination(CursorPagination):
    page_size = 100
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = ("name", "id")


class DashboardSavedViewPermission(BasePermission):
    message = "You don't have permission to access dashboard saved views."

    def has_permission(self, request: Request, view) -> bool:
        if not dashboard_saved_views_enabled(team=view.team):
            return False
        access_level = "viewer" if request.method in SAFE_METHODS else "editor"
        return UserAccessControl(user=request.user, team=view.team).check_access_level_for_resource(
            "dashboard", access_level
        )

    def has_object_permission(self, request: Request, view, obj: DashboardSavedView) -> bool:
        access_level = "viewer" if request.method in SAFE_METHODS else "editor"
        return UserAccessControl(user=request.user, team=view.team).check_access_level_for_resource(
            "dashboard", access_level
        )


class DashboardSavedViewViewSet(
    TeamAndOrgViewSetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    scope_object = "INTERNAL"
    permission_classes = [DashboardSavedViewPermission]
    pagination_class = DashboardSavedViewPagination
    queryset = DashboardSavedView.all_teams.all()
    serializer_class = DashboardSavedViewSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return DashboardSavedViewWriteSerializer
        return DashboardSavedViewSerializer

    @extend_schema(
        request=DashboardSavedViewWriteSerializer, responses={status.HTTP_201_CREATED: DashboardSavedViewSerializer}
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_serializer = DashboardSavedViewSerializer(serializer.instance, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def safely_get_queryset(self, queryset):
        return (
            queryset.filter(team_id=self.team.id)
            .filter(
                models.Q(scope=DashboardSavedView.Scope.TEAM)
                | models.Q(scope=DashboardSavedView.Scope.PRIVATE, created_by=self.request.user)
            )
            .select_related("created_by")
        )

    def perform_create(self, serializer):
        instance = serializer.save(team=self.team, created_by=self.request.user)
        report_user_action(
            self.request.user,
            "dashboard saved view created",
            {
                "saved_view_id": str(instance.id),
                "scope": instance.scope,
                **saved_view_filter_properties(instance.filters),
                **saved_view_creator_properties(team_id=self.team.id, user_id=self.request.user.id),
            },
            team=self.team,
            request=self.request,
        )

    def perform_update(self, serializer: DashboardSavedViewWriteSerializer) -> None:
        existing_view = serializer.instance
        scope = serializer.validated_data.get("scope")
        if (
            scope is not None
            and scope != existing_view.scope
            and existing_view.scope == DashboardSavedView.Scope.TEAM
            and existing_view.created_by_id != self.request.user.id
        ):
            raise PermissionDenied("Only the creator can change a shared saved view's visibility.")
        instance = serializer.save()
        report_user_action(
            self.request.user,
            "dashboard saved view updated",
            {
                "saved_view_id": str(instance.id),
                "scope": instance.scope,
                "changed_fields": sorted(serializer.validated_data.keys()),
                **saved_view_filter_properties(instance.filters),
            },
            team=self.team,
            request=self.request,
        )

    def perform_destroy(self, instance):
        report_user_action(
            self.request.user,
            "dashboard saved view deleted",
            {"saved_view_id": str(instance.id), "scope": instance.scope},
            team=self.team,
            request=self.request,
        )
        instance.delete()
