"""
Facade re-exports for repository selection.

The repo-selection agent picks a GitHub repository for a task given free-text context. Its
result type and errors are framework-free; other products call ``select_repository`` and
handle the typed outcomes.
"""

from products.tasks.backend.github_repository_access import inaccessible_repositories_via_integration
from products.tasks.backend.logic.repo_selection import (
    REPO_SELECTION_DUMMY_REPOSITORY,
    RepoSelectionRejectedError,
    RepoSelectionResult,
    RepoSelectionUnavailableError,
    list_team_connected_repositories,
    resolve_team_github_integration,
    select_repository,
)


def repository_accessible_via_integration(team_id: int, integration_id: int, repository: str) -> bool:
    return not inaccessible_repositories_via_integration(team_id, integration_id, [repository])


__all__ = [
    "REPO_SELECTION_DUMMY_REPOSITORY",
    "RepoSelectionRejectedError",
    "RepoSelectionResult",
    "RepoSelectionUnavailableError",
    "list_team_connected_repositories",
    "resolve_team_github_integration",
    "select_repository",
    "repository_accessible_via_integration",
]
