from types import SimpleNamespace

import pytest
from unittest.mock import patch

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.runs import (
    CreateWizardRunInput,
    MissingGithubIntegrationError,
    MissingRepositoryError,
    RepositoryNotAccessibleError,
    WizardRunStatus,
    WizardRunSurface,
)
from products.wizard.backend.models import WizardRun


@pytest.mark.django_db
def test_create_run_starts_queued(team, user) -> None:
    run = wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team.id,
            created_by_id=user.id,
            surface=WizardRunSurface.LOCAL,
        )
    )

    assert run.team_id == team.id
    assert run.created_by_id == user.id
    assert run.surface == WizardRunSurface.LOCAL
    assert run.status == WizardRunStatus.QUEUED
    assert run.outcome is None
    assert run.error_code is None


@pytest.mark.django_db
def test_cloud_run_requires_github_integration(team, user) -> None:
    with pytest.raises(MissingGithubIntegrationError):
        wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team.id,
                created_by_id=user.id,
                surface=WizardRunSurface.CLOUD,
                repository="posthog/posthog",
            )
        )

    assert not WizardRun.objects.filter(team_id=team.id).exists()


@pytest.mark.django_db
def test_cloud_run_requires_repository(team, user) -> None:
    with pytest.raises(MissingRepositoryError):
        wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team.id,
                created_by_id=user.id,
                surface=WizardRunSurface.CLOUD,
            )
        )


@pytest.mark.django_db
def test_cloud_run_rejects_inaccessible_repository(team, user) -> None:
    integration = SimpleNamespace(integration=SimpleNamespace(id=123))

    with (
        patch(
            "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration",
            return_value=integration,
        ),
        patch(
            "products.wizard.backend.logic.runs.repo_selection.repository_accessible_via_integration",
            return_value=False,
        ),
    ):
        with pytest.raises(RepositoryNotAccessibleError):
            wizard_facade.create_run(
                CreateWizardRunInput(
                    team_id=team.id, created_by_id=user.id, surface=WizardRunSurface.CLOUD, repository="private/example"
                )
            )


@pytest.mark.django_db
def test_cloud_run_stores_repository(team, user) -> None:
    integration = SimpleNamespace(integration=SimpleNamespace(id=123))

    with (
        patch(
            "products.wizard.backend.logic.runs.repo_selection.resolve_team_github_integration",
            return_value=integration,
        ),
        patch(
            "products.wizard.backend.logic.runs.repo_selection.repository_accessible_via_integration",
            return_value=False,
        ),
    ):
        run = wizard_facade.create_run(
            CreateWizardRunInput(
                team_id=team.id, created_by_id=user.id, surface=WizardRunSurface.CLOUD, repository="posthog/posthog"
            )
        )

        assert run.repository == "posthog/posthog"
