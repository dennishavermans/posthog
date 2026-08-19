from collections.abc import Callable
from uuid import UUID

import pytest
from unittest.mock import patch

from posthog.models import Team

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreateWizardRunInput,
    GitRepositoryWorkspace,
    LocalFolderWorkspace,
    WizardRunDTO,
)
from products.wizard.backend.facade.enums import WizardRunEnvironment, WizardRunErrorCode, WizardRunStatus
from products.wizard.backend.facade.errors import IllegalStatusTransitionError, WizardRunNotFoundError


def _create_local_run(team_id: int, user_id: int) -> WizardRunDTO:
    return wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team_id,
            created_by_id=user_id,
            environment=WizardRunEnvironment.LOCAL,
            workspace=LocalFolderWorkspace(project_name="example-project"),
        )
    )


def _create_cloud_run(team_id: int, user_id: int) -> WizardRunDTO:
    with (
        patch(
            "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration_id",
            return_value=123,
        ),
        patch(
            "products.wizard.backend.logic.runs.repo_selection.repository_accessible_via_integration",
            return_value=True,
        ),
    ):
        return wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team_id,
                created_by_id=user_id,
                environment=WizardRunEnvironment.CLOUD,
                workspace=GitRepositoryWorkspace(repository="posthog/posthog"),
            )
        )


@pytest.mark.django_db
def test_get_run_is_scoped_to_team(team, user) -> None:
    other_team = Team.objects.create(organization=team.organization, project=team.project, name="Other environment")
    created = _create_local_run(team.id, user.id)

    assert wizard_facade.get_run(team.id, created.id) == created

    with pytest.raises(WizardRunNotFoundError):
        wizard_facade.get_run(other_team.id, created.id)


@pytest.mark.django_db
def test_start_run_persists_running_status(team, user) -> None:
    created = _create_cloud_run(team.id, user.id)

    started = wizard_facade.start_run(team.id, created.id)

    assert started.status == WizardRunStatus.RUNNING
    assert wizard_facade.get_run(team.id, created.id) == started


@pytest.mark.parametrize(
    "transition_action, expected_status",
    (
        (wizard_facade.complete_run, WizardRunStatus.COMPLETED),
        (wizard_facade.cancel_run, WizardRunStatus.CANCELLED),
    ),
)
@pytest.mark.django_db
def test_running_run_persists_terminal_status(
    team,
    user,
    transition_action: Callable[[int, UUID], WizardRunDTO],
    expected_status: WizardRunStatus,
) -> None:
    created = _create_local_run(team.id, user.id)

    transitioned = transition_action(team.id, created.id)

    assert transitioned.status == expected_status
    assert wizard_facade.get_run(team.id, created.id) == transitioned


@pytest.mark.django_db
def test_fail_run_persists_error_code(team, user) -> None:
    created = _create_local_run(team.id, user.id)

    failed = wizard_facade.fail_run(team.id, created.id, error_code=WizardRunErrorCode.TIMEOUT)

    assert failed.status == WizardRunStatus.FAILED
    assert failed.error_code == WizardRunErrorCode.TIMEOUT
    assert wizard_facade.get_run(team.id, created.id) == failed


@pytest.mark.django_db
def test_invalid_persisted_transition_leaves_run_unchanged(team, user) -> None:
    created = _create_local_run(team.id, user.id)
    completed = wizard_facade.complete_run(team.id, created.id)

    with pytest.raises(IllegalStatusTransitionError):
        wizard_facade.cancel_run(team.id, created.id)

    assert wizard_facade.get_run(team.id, created.id) == completed


@pytest.mark.django_db
def test_transition_run_is_scoped_to_team(team, user) -> None:
    other_team = Team.objects.create(organization=team.organization, project=team.project, name="Other environment")
    created = _create_cloud_run(team.id, user.id)

    with pytest.raises(WizardRunNotFoundError):
        wizard_facade.start_run(other_team.id, created.id)

    assert wizard_facade.get_run(team.id, created.id) == created
