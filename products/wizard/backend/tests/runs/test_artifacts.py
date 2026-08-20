import pytest
from unittest.mock import patch

from posthog.models import Team

from products.wizard.backend.facade import api as wizard_facade
from products.wizard.backend.facade.contracts import (
    CreatePullRequestArtifactInput,
    CreateWizardRunInput,
    LocalFolderWorkspace,
    WizardRunDTO,
    WizardRunPullRequestArtifactDTO,
)
from products.wizard.backend.facade.enums import WizardRunArtifactType, WizardRunEnvironment
from products.wizard.backend.facade.errors import WizardRunNotFoundError


def _create_run(team_id: int, user_id: int) -> WizardRunDTO:
    return wizard_facade.create_run(
        CreateWizardRunInput(
            team_id=team_id,
            created_by_id=user_id,
            environment=WizardRunEnvironment.LOCAL,
            workspace=LocalFolderWorkspace(project_name="example-project"),
        )
    )


@pytest.mark.django_db
def test_create_git_diff_artifact_stores_content_by_reference(team, user) -> None:
    run = _create_run(team.id, user.id)
    diff = b"diff --git a/app.py b/app.py\n"

    with patch("products.wizard.backend.logic.artifacts.object_storage.write") as write:
        artifact = wizard_facade.create_git_diff_artifact(team.id, run.id, diff)

    assert artifact is not None
    assert artifact.team_id == team.id
    assert artifact.run_id == run.id
    assert artifact.artifact_type == WizardRunArtifactType.GIT_DIFF
    assert artifact.size_bytes == len(diff)
    write.assert_called_once_with(
        f"wizard/runs/team_{team.id}/run_{run.id}/artifacts/git.diff",
        diff,
        extras={"ContentType": "text/x-diff; charset=utf-8"},
    )
    assert wizard_facade.list_run_artifacts(team.id, run.id) == [artifact]


@pytest.mark.django_db
def test_empty_git_diff_creates_no_artifact(team, user) -> None:
    run = _create_run(team.id, user.id)

    with patch("products.wizard.backend.logic.artifacts.object_storage.write") as write:
        artifact = wizard_facade.create_git_diff_artifact(team.id, run.id, b"")

    assert artifact is None
    assert wizard_facade.list_run_artifacts(team.id, run.id) == []
    write.assert_not_called()


@pytest.mark.django_db
def test_git_diff_artifact_is_idempotent_for_run(team, user) -> None:
    run = _create_run(team.id, user.id)

    with patch("products.wizard.backend.logic.artifacts.object_storage.write"):
        first = wizard_facade.create_git_diff_artifact(team.id, run.id, b"first")
        second = wizard_facade.create_git_diff_artifact(team.id, run.id, b"second")

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert second.size_bytes == len(b"second")
    assert wizard_facade.list_run_artifacts(team.id, run.id) == [second]


@pytest.mark.django_db
def test_create_git_diff_artifact_is_scoped_to_team(team, user) -> None:
    other_team = Team.objects.create(organization=team.organization, project=team.project, name="Other environment")
    run = _create_run(team.id, user.id)

    with (
        patch("products.wizard.backend.logic.artifacts.object_storage.write") as write,
        pytest.raises(WizardRunNotFoundError),
    ):
        wizard_facade.create_git_diff_artifact(other_team.id, run.id, b"diff")

    write.assert_not_called()


@pytest.mark.django_db
def test_create_pull_request_artifact_persists_pull_request_identity(team, user) -> None:
    run = _create_run(team.id, user.id)
    params = CreatePullRequestArtifactInput(
        team_id=team.id,
        run_id=run.id,
        url="https://github.com/posthog/posthog/pull/123",
        number=123,
        repository="posthog/posthog",
        head_branch="posthog/wizard-123",
        base_branch="master",
    )

    artifact = wizard_facade.create_pull_request_artifact(params)

    assert isinstance(artifact, WizardRunPullRequestArtifactDTO)
    assert artifact.artifact_type == WizardRunArtifactType.PULL_REQUEST
    assert artifact.url == params.url
    assert artifact.number == params.number
    assert artifact.repository == params.repository
    assert artifact.head_branch == params.head_branch
    assert artifact.base_branch == params.base_branch
    assert wizard_facade.list_run_artifacts(team.id, run.id) == [artifact]
