import pytest

from products.wizard.backend.facade.contracts import GitRepositoryWorkspace, LocalFolderWorkspace, WizardWorkspace
from products.wizard.backend.facade.enums import WizardRunEnvironment
from products.wizard.backend.facade.errors import InvalidWorkspaceEnvironmentError
from products.wizard.backend.logic.runs.workspaces import validate_workspace_environment


@pytest.mark.parametrize(
    ("workspace_class", "metadata", "expected_workspace"),
    [
        (
            LocalFolderWorkspace,
            {"project_name": "example-project"},
            LocalFolderWorkspace(project_name="example-project"),
        ),
        (
            GitRepositoryWorkspace,
            {"repository": "posthog/posthog"},
            GitRepositoryWorkspace(repository="posthog/posthog"),
        ),
    ],
)
def test_workspace_serialization_round_trip(
    workspace_class: type[LocalFolderWorkspace] | type[GitRepositoryWorkspace],
    metadata: dict[str, str],
    expected_workspace: WizardWorkspace,
) -> None:
    workspace = workspace_class.from_dict(metadata)

    assert workspace == expected_workspace
    assert workspace.to_dict() == metadata


@pytest.mark.parametrize(
    ("workspace_class", "metadata"),
    [
        (LocalFolderWorkspace, {"project_name": 123}),
        (GitRepositoryWorkspace, {"repository": None}),
    ],
)
def test_workspace_rejects_invalid_serialized_value(
    workspace_class: type[LocalFolderWorkspace] | type[GitRepositoryWorkspace], metadata: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        workspace_class.from_dict(metadata)


@pytest.mark.parametrize(
    ("environment", "workspace"),
    [
        (WizardRunEnvironment.LOCAL, LocalFolderWorkspace(project_name="example-project")),
        (WizardRunEnvironment.CLOUD, GitRepositoryWorkspace(repository="posthog/posthog")),
    ],
)
def test_environment_accepts_supported_workspace(environment: WizardRunEnvironment, workspace: WizardWorkspace) -> None:
    validate_workspace_environment(environment, workspace)


@pytest.mark.parametrize(
    ("environment", "workspace"),
    [
        (WizardRunEnvironment.LOCAL, GitRepositoryWorkspace(repository="posthog/posthog")),
        (WizardRunEnvironment.CLOUD, LocalFolderWorkspace(project_name="example-project")),
    ],
)
def test_environment_rejects_unsupported_workspace(
    environment: WizardRunEnvironment, workspace: WizardWorkspace
) -> None:
    with pytest.raises(InvalidWorkspaceEnvironmentError):
        validate_workspace_environment(environment, workspace)
