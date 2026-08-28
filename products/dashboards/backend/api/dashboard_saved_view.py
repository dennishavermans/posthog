import json
from collections.abc import Mapping
from typing import Literal, TypedDict, cast

from django.db import models, transaction
from django.db.models import QuerySet

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from posthog.api.routing import TeamAndOrgViewSetMixin
from posthog.event_usage import report_user_action
from posthog.helpers.trigram_search import MAX_SEARCH_LENGTH
from posthog.models.user import User

from products.access_control.backend.facade.user_access_control import UserAccessControl
from products.dashboards.backend.feature_flags import dashboard_saved_views_enabled
from products.dashboards.backend.models.dashboard import Dashboard
from products.dashboards.backend.models.dashboard_saved_view import DashboardSavedView

SAVED_VIEW_FILTER_KEYS = {"search", "createdBy", "pinned", "shared", "tags", "folder"}
MAX_SAVED_VIEW_FILTER_BYTES = 16 * 1024
MAX_SAVED_VIEW_FILTER_STRING_LENGTH = MAX_SEARCH_LENGTH
MAX_SAVED_VIEW_TAGS = 50
MAX_SAVED_VIEW_TAG_LENGTH = 100
MAX_SAVED_VIEW_CREATORS = 100


class DashboardSavedViewFilters(TypedDict, total=False):
    search: str
    createdBy: list[int] | Literal["All users"]
    pinned: bool
    shared: bool
    tags: list[str]
    folder: str | None


def saved_view_filter_properties(filters: Mapping[str, object]) -> dict[str, bool | int]:
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


def has_saved_view_filters(filters: Mapping[str, object]) -> bool:
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

    def validate_filters(self, value: object) -> DashboardSavedViewFilters:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filters must be an object")
        filters = cast(dict[str, object], value)
        unsupported_keys = filters.keys() - SAVED_VIEW_FILTER_KEYS
        if unsupported_keys:
            raise serializers.ValidationError("Filters contain unsupported fields.")
        if "search" in filters and not isinstance(filters["search"], str):
            raise serializers.ValidationError("Search must be a string.")
        if (
            isinstance(filters.get("search"), str)
            and len(cast(str, filters["search"])) > MAX_SAVED_VIEW_FILTER_STRING_LENGTH
        ):
            raise serializers.ValidationError("Search must be 200 characters or fewer.")
        if "createdBy" in filters and filters["createdBy"] != "All users":
            creators = filters["createdBy"]
            if not isinstance(creators, list) or any(type(creator) is not int for creator in creators):
                raise serializers.ValidationError("Creators must be a list of user IDs.")
            if len(creators) > MAX_SAVED_VIEW_CREATORS:
                raise serializers.ValidationError("You can select up to 100 creators.")
        if "pinned" in filters and not isinstance(filters["pinned"], bool):
            raise serializers.ValidationError("Pinned must be true or false.")
        if "shared" in filters and not isinstance(filters["shared"], bool):
            raise serializers.ValidationError("Shared must be true or false.")
        if "tags" in filters and (
            not isinstance(filters["tags"], list) or any(not isinstance(tag, str) for tag in filters["tags"])
        ):
            raise serializers.ValidationError("Tags must be a list of strings.")
        if isinstance(filters.get("tags"), list):
            tags = cast(list[str], filters["tags"])
            if len(tags) > MAX_SAVED_VIEW_TAGS:
                raise serializers.ValidationError("You can select up to 50 tags.")
            if any(len(tag) > MAX_SAVED_VIEW_TAG_LENGTH for tag in tags):
                raise serializers.ValidationError("Tags must be 100 characters or fewer.")
        if "folder" in filters and filters["folder"] is not None and not isinstance(filters["folder"], str):
            raise serializers.ValidationError("Folder must be a string or null.")
        if (
            isinstance(filters.get("folder"), str)
            and len(cast(str, filters["folder"])) > MAX_SAVED_VIEW_FILTER_STRING_LENGTH
        ):
            raise serializers.ValidationError("Folder must be 200 characters or fewer.")
        if not has_saved_view_filters(filters):
            raise serializers.ValidationError("Add at least one filter before saving a view.")
        if (
            len(json.dumps(filters, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            > MAX_SAVED_VIEW_FILTER_BYTES
        ):
            raise serializers.ValidationError("Saved view filters are too large.")
        return cast(DashboardSavedViewFilters, filters)


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

    def has_permission(self, request: Request, view: "DashboardSavedViewViewSet") -> bool:
        if not dashboard_saved_views_enabled(team=view.team):
            return False
        access_level = "viewer" if request.method in SAFE_METHODS else "editor"
        return UserAccessControl(user=cast(User, request.user), team=view.team).check_access_level_for_resource(
            "dashboard", access_level
        )

    def has_object_permission(
        self, request: Request, view: "DashboardSavedViewViewSet", obj: DashboardSavedView
    ) -> bool:
        access_level = "viewer" if request.method in SAFE_METHODS else "editor"
        return UserAccessControl(user=cast(User, request.user), team=view.team).check_access_level_for_resource(
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
    queryset: QuerySet[DashboardSavedView] = DashboardSavedView.all_teams.all()
    serializer_class = DashboardSavedViewSerializer

    def get_serializer_class(self) -> type[DashboardSavedViewWriteSerializer | DashboardSavedViewSerializer]:
        if self.action == "create":
            return DashboardSavedViewWriteSerializer
        return DashboardSavedViewSerializer

    @extend_schema(
        request=DashboardSavedViewWriteSerializer, responses={status.HTTP_201_CREATED: DashboardSavedViewSerializer}
    )
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = DashboardSavedViewWriteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        response_serializer = DashboardSavedViewSerializer(serializer.instance, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def safely_get_queryset(self, queryset: QuerySet[DashboardSavedView]) -> QuerySet[DashboardSavedView]:
        return (
            queryset.filter(team_id=self.canonical_team_id)
            .filter(
                models.Q(scope=DashboardSavedView.Scope.TEAM)
                | models.Q(scope=DashboardSavedView.Scope.PRIVATE, created_by=cast(User, self.request.user))
            )
            .select_related("created_by")
        )

    @property
    def canonical_team_id(self) -> int:
        return self.team.parent_team_id or self.team.id

    def _should_skip_parents_filter(self) -> bool:
        return True

    def perform_create(self, serializer: DashboardSavedViewWriteSerializer) -> None:
        instance = serializer.save(team=self.team, created_by=self.request.user)
        report_user_action(
            self.request.user,
            "dashboard saved view created",
            {
                "saved_view_id": str(instance.id),
                "scope": instance.scope,
                **saved_view_filter_properties(cast(DashboardSavedViewFilters, instance.filters)),
                **saved_view_creator_properties(
                    team_id=self.canonical_team_id, user_id=cast(User, self.request.user).id
                ),
            },
            team=self.team,
            request=self.request,
        )

    def perform_update(self, serializer: DashboardSavedViewWriteSerializer) -> None:
        existing_view = cast(DashboardSavedView, serializer.instance)
        try:
            with transaction.atomic():
                locked_view = DashboardSavedView.all_teams.select_for_update().get(pk=existing_view.pk)
                scope = cast(DashboardSavedView.Scope | None, serializer.validated_data.get("scope"))
                if (
                    locked_view.scope == DashboardSavedView.Scope.PRIVATE
                    and locked_view.created_by_id != self.request.user.id
                ):
                    raise PermissionDenied("You don't have permission to update this private saved view.")
                if (
                    scope is not None
                    and scope != locked_view.scope
                    and locked_view.scope == DashboardSavedView.Scope.TEAM
                    and locked_view.created_by_id != self.request.user.id
                ):
                    raise PermissionDenied("Only the creator can change a shared saved view's visibility.")
                serializer.instance = locked_view
                instance = serializer.save()
        except DashboardSavedView.DoesNotExist:
            raise NotFound()
        report_user_action(
            self.request.user,
            "dashboard saved view updated",
            {
                "saved_view_id": str(instance.id),
                "scope": instance.scope,
                "changed_fields": sorted(serializer.validated_data.keys()),
                **saved_view_filter_properties(cast(DashboardSavedViewFilters, instance.filters)),
            },
            team=self.team,
            request=self.request,
        )

    def perform_destroy(self, instance: DashboardSavedView) -> None:
        try:
            with transaction.atomic():
                locked_view = DashboardSavedView.all_teams.select_for_update().get(pk=instance.pk)
                if (
                    locked_view.scope == DashboardSavedView.Scope.PRIVATE
                    and locked_view.created_by_id != self.request.user.id
                ):
                    raise PermissionDenied("You don't have permission to delete this private saved view.")
                scope = locked_view.scope
                locked_view.delete()
        except DashboardSavedView.DoesNotExist:
            raise NotFound()
        report_user_action(
            self.request.user,
            "dashboard saved view deleted",
            {"saved_view_id": str(instance.id), "scope": scope},
            team=self.team,
            request=self.request,
        )
